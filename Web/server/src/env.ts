import { z } from "zod";

// Blank values in .env files mean "not set".
const blankToUndefined = (value: unknown) => (value === "" ? undefined : value);
const optional = <T extends z.ZodType>(schema: T) =>
  z.preprocess(blankToUndefined, schema.optional());

const envSchema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().min(1).max(65535).default(8788),
  /** Directory of the built web app. Set in the container image; unset in local dev (Vite serves it). */
  STATIC_DIR: optional(z.string()),
  APP_COMMIT: z.string().default("dev"),
  DATABASE_URL: optional(z.string()),
  OPENROUTER_API_KEY: optional(z.string()),

  /** Base URL of the Framebase Cloudflare API Worker for the library being browsed. */
  FRAMEBASE_CLOUD_API_URL: optional(z.url()),
  /** The Worker's pairing credential. Used only to enroll this server as a read-only device. */
  FRAMEBASE_CLOUD_PAIRING_SECRET: optional(z.string()),
  /** A second library (Personal), served by its own Worker. Libraries are never merged. */
  FRAMEBASE_PERSONAL_API_URL: optional(z.url()),
  FRAMEBASE_PERSONAL_PAIRING_SECRET: optional(z.string()),
  /** Stable ID for this server's device record on the Worker. */
  FRAMEBASE_WEB_DEVICE_ID: z.string().min(3).max(128).default("framebase-web-studio"),
  /**
   * Set to true only when an authentication layer (Cloudflare Access, Entra/Easy Auth) sits in front of
   * this server. In production the library routes stay disabled until you assert that, because they
   * serve private media with no sign-in of their own.
   */
  LIBRARY_ACCESS_PROTECTED: z.preprocess(blankToUndefined, z.stringbool().default(false)),
  /**
   * Allow edits to the library (rename, favorite, rating, tags, move, Trash and restore). Off by default.
   * When on, this server enrolls with the extra scopes those edits need; permanent deletion is never offered.
   */
  LIBRARY_WRITES_ENABLED: z.preprocess(blankToUndefined, z.stringbool().default(false)),
});

export type Env = z.infer<typeof envSchema>;

export function loadEnv(source: Record<string, string | undefined> = process.env): Env {
  return envSchema.parse(source);
}
