import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI service and adds the
// X-API-Key from lexicon/.env on the server side, so the key never
// reaches the browser bundle.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "LEXICON_");
  const port = env.LEXICON_API_PORT || "8770";
  return {
    plugins: [react()],
    base: "/ui/",
    server: {
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${port}`,
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ""),
          headers: env.LEXICON_API_KEY ? { "X-API-Key": env.LEXICON_API_KEY } : {},
        },
        // Read-only pack entry for the learner-app simulator (問題回報 #758):
        // only the two GET endpoints the simulator downloads from the app
        // server on 8123, so agents can reach the live pack through 5173.
        "^/app-pack/(lexicon|decks)(\\?|$)": {
          target: "http://127.0.0.1:8123",
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/app-pack/, "/api"),
        },
      },
    },
  };
});
