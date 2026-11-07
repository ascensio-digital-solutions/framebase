import { Hono } from "hono";
import { secureHeaders } from "hono/secure-headers";
import { serveStatic } from "@hono/node-server/serve-static";
import { commandEnvelopeSchema } from "@framebase/web-contracts";
import type { Env } from "./env";

const SERVICE = "framebase-web";

/**
 * The browser only ever talks to this server. Cloudflare, OpenRouter and PostgreSQL credentials
 * stay server-side so the existing native API security boundary is preserved.
 */
export function createApp(env: Env) {
  const app = new Hono();

  app.use("*", secureHeaders());

  app.get("/healthz", (c) => c.json({ status: "ok", service: SERVICE, commit: env.APP_COMMIT }));

  // Reports which integrations are configured. Never returns values.
  app.get("/v1/config", (c) =>
    c.json({
      providers: {
        openrouter: Boolean(env.OPENROUTER_API_KEY),
        cloudCatalog: Boolean(env.FRAMEBASE_CLOUD_API_URL && env.FRAMEBASE_CLOUD_API_TOKEN),
        database: Boolean(env.DATABASE_URL),
      },
    }),
  );

  // Validates the typed command envelope. Execution lands with the library workspace milestone,
  // so a valid envelope is acknowledged as not implemented rather than pretending to apply.
  app.post("/v1/commands", async (c) => {
    let body: unknown;
    try {
      body = await c.req.json();
    } catch {
      return c.json({ error: "invalid_json" }, 400);
    }
    const parsed = commandEnvelopeSchema.safeParse(body);
    if (!parsed.success) {
      return c.json(
        {
          error: "invalid_command",
          issues: parsed.error.issues.map((issue) => ({
            path: issue.path.join("."),
            message: issue.message,
          })),
        },
        400,
      );
    }
    return c.json(
      {
        error: "not_implemented",
        operationId: parsed.data.operationId,
        command: parsed.data.command.name,
      },
      501,
    );
  });

  app.all("/v1/*", (c) => c.json({ error: "not_found" }, 404));

  if (env.STATIC_DIR) {
    const root = env.STATIC_DIR;
    app.use("*", serveStatic({ root }));
    // Single-page app fallback for client-side routes.
    app.get("*", serveStatic({ root, path: "index.html" }));
  }

  return app;
}
