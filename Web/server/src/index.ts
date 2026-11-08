import { serve } from "@hono/node-server";
import { createApp } from "./app";
import { loadEnv } from "./env";

const env = loadEnv();
const server = serve({ fetch: createApp(env, { warmUp: true }).fetch, port: env.PORT }, (info) => {
  console.log(`framebase-web listening on :${info.port} (${env.NODE_ENV})`);
});

// Container Apps sends SIGTERM on scale-in and revision swaps.
for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    server.close(() => process.exit(0));
  });
}
