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
  FRAMEBASE_CLOUD_API_URL: optional(z.url()),
  FRAMEBASE_CLOUD_API_TOKEN: optional(z.string()),
});

export type Env = z.infer<typeof envSchema>;

export function loadEnv(source: Record<string, string | undefined> = process.env): Env {
  return envSchema.parse(source);
}
