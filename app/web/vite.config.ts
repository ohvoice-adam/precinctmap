import { defineConfig } from "vitest/config";

// Dev server proxies /api to the FastAPI app on :8000, so the client always uses relative URLs.
export default defineConfig({
  // Read VITE_* settings (e.g. VITE_ORG_NAME) from the repo-root .env; only VITE_* reach the client.
  envDir: "../..",
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  // MapLibre alone is ~1 MB minified (~270 kB gzip); the limit keeps real regressions visible.
  build: {
    outDir: "dist",
    sourcemap: true,
    chunkSizeWarningLimit: 1200,
    // Two pages: the public map and the admin upload page (served behind the admin login).
    rolldownOptions: { input: { main: "index.html", admin: "admin.html" } },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts"] },
});
