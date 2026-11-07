# Framebase Web Studio

Browser workspace for Framebase: Explorer, **Create** chat, central Grid/List/Board workspace, **Understand** chat. Plan and gates: [`docs/phases/PHASE_10_WEB_STUDIO.md`](../docs/phases/PHASE_10_WEB_STUDIO.md).

## Layout

| Path                 | What it is                                                                       |
| -------------------- | -------------------------------------------------------------------------------- |
| `app/`               | React + Vite shell (resizable, collapsible panels). Placeholders for the chats.  |
| `server/`            | Hono API. Serves the built app in production. Holds all server-side credentials. |
| `packages/contracts` | Zod schemas for commands, receipts and workspace events shared by UI and agents. |

## Develop

Open the repo in a Codespace (or the dev container); `post-create.sh` installs everything.

```bash
cd Web
npm run dev      # app on :5173, API on :8788 (the app proxies /healthz and /v1)
npm run check    # typecheck + lint + tests
npm run build    # server bundle + app build
```

Local settings live in `Web/.env.local` (copied from `.env.example`, git-ignored). In a Codespace, set `OPENROUTER_API_KEY`, `FRAMEBASE_CLOUD_API_URL` and `FRAMEBASE_CLOUD_API_TOKEN` as Codespaces secrets.

## Container

```bash
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t framebase-web Web
docker run --rm -p 8080:8080 framebase-web
```

Publishing to Azure Container Registry is the manual `web-image` workflow; it never deploys.

## What is real today

- `GET /healthz`, `GET /v1/config` (which integrations are configured, never their values).
- `POST /v1/commands` validates the typed envelope and returns `501 not_implemented` for valid commands. Execution arrives with the library workspace milestone.
- The chats, catalog views and board are static shells and say so in the UI.
