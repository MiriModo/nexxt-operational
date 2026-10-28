import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dezvoltare: datele vin din public/data/*.json (copii ale out/).
// Când apare API-ul (pasul 4), /api se proxy-ază către FastAPI, iar stratul src/api comută sursa.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
