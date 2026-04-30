import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

function resolveManualChunk(id: string) {
  const normalizedId = id.replace(/\\/g, "/");

  if (normalizedId.includes("/node_modules/react-router")) {
    return "router-vendor";
  }
  if (
    normalizedId.includes("/node_modules/react/") ||
    normalizedId.includes("/node_modules/react-dom/")
  ) {
    return "react-vendor";
  }
  if (normalizedId.includes("node_modules")) {
    return "vendor";
  }
  if (
    normalizedId.includes("/src/components/layout/") ||
    normalizedId.includes("/src/context/") ||
    normalizedId.includes("/src/hooks/useThemeMode") ||
    normalizedId.includes("/src/hooks/useConnection") ||
    normalizedId.includes("/src/hooks/useMarcadoseConnection")
  ) {
    return "app-shell";
  }
  if (
    normalizedId.includes("/src/pages/QueryBuilderPage") ||
    normalizedId.includes("/src/pages/MarcadoseQueryBuilderPage") ||
    normalizedId.includes("/src/components/query/")
  ) {
    return "query-builder";
  }
  if (
    normalizedId.includes("/src/pages/DriveDownloadPage") ||
    normalizedId.includes("/src/pages/UploadMasterDrivePage") ||
    normalizedId.includes("/src/components/drive/")
  ) {
    return "drive-ops";
  }
  if (
    normalizedId.includes("/src/pages/SidebarToolsPage") ||
    normalizedId.includes("/src/pages/FtpDownloadPage")
  ) {
    return "operations";
  }
  if (
    normalizedId.includes("/src/pages/MergeEnrichPage") ||
    normalizedId.includes("/src/pages/FolderMergePage")
  ) {
    return "data-workflows";
  }
  return undefined;
}

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
    manifest: true,
    rollupOptions: {
      output: {
        manualChunks: resolveManualChunk,
      },
    },
  },
  server: {
    port: 5173,
    watch: {
      ignored: [
        "**/frontend_dist/**",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
      ],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8741",
        changeOrigin: true,
      },
    },
  },
});
