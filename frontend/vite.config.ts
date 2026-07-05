import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev proxy target defaults to a local backend on 8001 (same-machine
// development). To point at a remote backend (e.g. ICRN through a
// localtunnel/ngrok URL), set VITE_API_TARGET in the environment:
//
//   VITE_API_TARGET=https://green-poets-sniff.loca.lt npm run dev
//
// Or drop the same line into frontend/.env.local (git-ignored). Streaming
// works over localtunnel because it's a raw HTTP pass-through; the free
// tier does show a one-time "Click to Continue" warning page that must be
// dismissed in a browser tab first, otherwise proxied requests get the
// HTML warning back instead of JSON.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://localhost:8001";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          secure: true,
          // Bypass the localtunnel "reminder" page for proxied API calls.
          // Only affects requests going through Vite's proxy; the browser
          // must still dismiss the warning page once for the tunnel URL.
          headers: {
            "bypass-tunnel-reminder": "true",
          },
        },
      },
    },
  };
});
