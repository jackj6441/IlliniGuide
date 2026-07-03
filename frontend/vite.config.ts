import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Frontend dev server runs on 5173 and proxies /api to the FastAPI backend on 8001.
// Streaming needs `changeOrigin` + no buffering; Vite's default proxy already streams.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
});
