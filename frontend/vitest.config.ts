import path from "path";
import { mergeConfig, defineConfig } from "vitest/config";
import viteConfig from "./vite.config";

export default mergeConfig(
  viteConfig,
  defineConfig({
    resolve: {
      alias: {
        "msw/node": path.resolve(__dirname, "./node_modules/msw/lib/node/index.mjs"),
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      css: true,
      setupFiles: ["./vitest.setup.ts"],
      include: ["./tests/**/*.test.tsx"],
      clearMocks: true,
    },
  }),
);
