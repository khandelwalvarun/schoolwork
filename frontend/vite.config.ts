import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 7778,
    strictPort: true,
    allowedHosts: true,
    cors: true,
    proxy: {
      "/api": "http://127.0.0.1:7777",
      "/mcp": "http://127.0.0.1:7777",
      "/health": "http://127.0.0.1:7777",
    },
  },
});
