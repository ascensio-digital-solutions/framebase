import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const api = process.env.WEB_API_URL ?? "http://localhost:8788";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Listen on all interfaces so Codespaces port forwarding can reach the dev server.
    host: true,
    proxy: { "/healthz": api, "/v1": api },
  },
  test: { environment: "node" },
});
