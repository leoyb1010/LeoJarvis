import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // rolldown 的 manualChunks 需函数形式：按模块路径归拢 vendor 块，利于浏览器长缓存。
        manualChunks(id: string) {
          if (id.includes("node_modules")) {
            if (id.includes("@xterm")) return "xterm";          // 终端依赖（随懒加载分块，再显式归拢）
            if (id.includes("react")) return "react";           // React 运行时单独成块
          }
          return undefined;
        },
      },
    },
  },
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
