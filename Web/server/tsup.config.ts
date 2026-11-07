import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  platform: "node",
  target: "node22",
  clean: true,
  sourcemap: true,
  // Workspace contracts ship as TypeScript source, so they are bundled in.
  noExternal: ["@framebase/web-contracts"],
});
