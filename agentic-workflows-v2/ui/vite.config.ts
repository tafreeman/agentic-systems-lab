import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");
  const apiProxyTarget =
    env.VITE_API_PROXY_TARGET || process.env.VITE_API_PROXY_TARGET || "http://localhost:8010";
  const wsProxyTarget = apiProxyTarget.replace(/^http/i, "ws");
  const workflowBuilderFlag =
    env.VITE_AGENTIC_ENABLE_WORKFLOW_BUILDER ??
    env.AGENTIC_ENABLE_WORKFLOW_BUILDER ??
    process.env.VITE_AGENTIC_ENABLE_WORKFLOW_BUILDER ??
    process.env.AGENTIC_ENABLE_WORKFLOW_BUILDER ??
    "";

  return {
    plugins: [react()],
    define: {
      __AGENTIC_ENABLE_WORKFLOW_BUILDER__: JSON.stringify(workflowBuilderFlag),
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": apiProxyTarget,
        "/ws": {
          target: wsProxyTarget,
          ws: true,
        },
      },
    },
  };
});
