import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dezvoltare: /api se proxy-ază către FastAPI (python -m retailagent.api); fără API, stratul src/api
// comută singur pe snapshot-ul static din public/data/demo.json. API_TARGET (env sau .env) schimbă adresa API-ului.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "API_");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": { target: env.API_TARGET || "http://127.0.0.1:8000", changeOrigin: true } },
    },
  };
});
