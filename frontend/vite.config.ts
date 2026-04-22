import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

/**
 * Vite configuration for the DuckDB Data Dashboard frontend.
 *
 * - Outputs the production build to ../frontend_dist/ (consumed by PyInstaller).
 * - Proxies /api requests to the FastAPI backend during development.
 * - Resolves @/* path aliases to src/*.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../frontend_dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8741",
        changeOrigin: true,
      },
    },
  },
});
