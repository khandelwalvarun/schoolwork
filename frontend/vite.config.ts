import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 7778,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:7777",
      "/mcp": "http://localhost:7777",
      "/health": "http://localhost:7777",
    },
  },
});
