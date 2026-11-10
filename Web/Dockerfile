# syntax=docker/dockerfile:1
# Single image: Hono API + the built React app. Build context is the Web/ directory.
#   docker build -t framebase-web --build-arg GIT_SHA=$(git rev-parse HEAD) Web

FROM node:22-bookworm-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
COPY packages/contracts/package.json packages/contracts/
COPY server/package.json server/
COPY app/package.json app/
RUN npm ci
COPY . .
RUN npm run build
# Everything the runtime needs is bundled (server) or static (app); drop dev dependencies.
RUN npm prune --omit=dev

FROM node:22-bookworm-slim AS runtime
ARG GIT_SHA=dev
ENV NODE_ENV=production \
    PORT=8080 \
    STATIC_DIR=/srv/public \
    APP_COMMIT=${GIT_SHA}
WORKDIR /srv
COPY --from=build /web/node_modules ./node_modules
COPY --from=build /web/server/package.json ./server/package.json
COPY --from=build /web/server/dist ./server/dist
COPY --from=build /web/app/dist ./public
USER node
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD node -e "fetch('http://127.0.0.1:'+process.env.PORT+'/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "server/dist/index.js"]
