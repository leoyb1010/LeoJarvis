import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8787", changeOrigin: true },
      "/settings": "http://127.0.0.1:8787",
      "/system": "http://127.0.0.1:8787",
      "/devices": "http://127.0.0.1:8787",
      "/device": "http://127.0.0.1:8787",
      "/briefing": "http://127.0.0.1:8787",
      "/intelligence": "http://127.0.0.1:8787",
      "/cockpit": "http://127.0.0.1:8787",
      "/personal-notes": "http://127.0.0.1:8787",
      "/memories": "http://127.0.0.1:8787",
      "/memory": "http://127.0.0.1:8787",
      "/ingest": "http://127.0.0.1:8787",
      "/events": "http://127.0.0.1:8787",
      "/services": "http://127.0.0.1:8787",
      "/agents": "http://127.0.0.1:8787",
      "/agent": "http://127.0.0.1:8787",
      "/journal": "http://127.0.0.1:8787",
      "/feedback": "http://127.0.0.1:8787",
      "/ws": { target: "ws://127.0.0.1:8787", ws: true },
    },
  },
});
