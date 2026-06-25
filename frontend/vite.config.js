import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the API runs on :8000; proxy /api there so the frontend
// can use same-origin relative URLs in both dev and production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist" },
});
