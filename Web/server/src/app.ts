import { Hono } from "hono";
import { secureHeaders } from "hono/secure-headers";
import { serveStatic } from "@hono/node-server/serve-static";
import { commandEnvelopeSchema } from "@framebase/web-contracts";
import { CloudClient } from "./cloud/client";
import type { Env } from "./env";
import { createLibraryRoutes } from "./library";

const SERVICE = "framebase-web";

export interface LibraryDef {
  id: string;
  label: string;
  cloud: CloudClient;
}

export interface AppDeps {
  /** Injected in tests: a single library. */
  cloud?: CloudClient;
  /** Injected in tests: several libraries. */
  libraries?: LibraryDef[];
  /** Load the catalog in the background at startup. Enabled by the real server, not by tests. */
  warmUp?: boolean;
}

/** Libraries configured in the environment. Each has its own Worker, device identity and credentials. */
function librariesFromEnv(env: Env): LibraryDef[] {
  // Least privilege: read-only unless edits are explicitly enabled. Permanent deletion is never requested.
  const scopes = env.LIBRARY_WRITES_ENABLED
    ? ["library.read", "assets.metadata.write", "assets.organize", "trash.write"]
    : ["library.read"];
  const make = (id: string, label: string, baseUrl?: string, pairingSecret?: string) =>
    baseUrl && pairingSecret
      ? [
          {
            id,
            label,
            cloud: new CloudClient({
              baseUrl,
              pairingSecret,
              deviceId: env.FRAMEBASE_WEB_DEVICE_ID,
              scopes,
            }),
          },
        ]
      : [];
  return [
    ...make("hsc", "HSC Library", env.FRAMEBASE_CLOUD_API_URL, env.FRAMEBASE_CLOUD_PAIRING_SECRET),
    ...make(
      "personal",
      "Personal Library",
      env.FRAMEBASE_PERSONAL_API_URL,
      env.FRAMEBASE_PERSONAL_PAIRING_SECRET,
    ),
  ];
}

/**
 * The browser only ever talks to this server. Cloudflare, OpenRouter and PostgreSQL credentials
 * stay server-side so the existing native API security boundary is preserved.
 */
export function createApp(env: Env, deps: AppDeps = {}) {
  const app = new Hono();

  const libraries: LibraryDef[] =
    deps.libraries ??
    (deps.cloud ? [{ id: "library", label: "Library", cloud: deps.cloud }] : librariesFromEnv(env));

  app.use("*", secureHeaders());

  app.get("/healthz", (c) => c.json({ status: "ok", service: SERVICE, commit: env.APP_COMMIT }));

  // Reports which integrations are configured. Never returns values.
  app.get("/v1/config", (c) =>
    c.json({
      providers: {
        openrouter: Boolean(env.OPENROUTER_API_KEY),
        cloudCatalog: libraries.length > 0,
        database: Boolean(env.DATABASE_URL),
      },
      library: { writes: libraries.length > 0 && env.LIBRARY_WRITES_ENABLED },
      // Each library is separate: its own catalog, search and edits. Nothing is merged across libraries.
      libraries: libraries.map(({ id, label }) => ({ id, label })),
    }),
  );

  if (libraries.length === 0) {
    app.route("/v1/library", createLibraryRoutes(env, undefined)); // answers 503 cloud_not_configured
  }
  libraries.forEach((lib, i) => {
    const routes = createLibraryRoutes(env, lib.cloud, { warmUp: deps.warmUp });
    app.route(`/v1/libraries/${lib.id}`, routes);
    if (i === 0) app.route("/v1/library", routes); // the first library is the default
  });

  // Validates the typed command envelope. Execution lands with the connected-agents milestone,
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
