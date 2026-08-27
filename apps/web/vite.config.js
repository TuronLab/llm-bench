import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-server proxy so `npm run dev` can talk to a locally running API service
// without CORS friction; in production the nginx container performs the
// equivalent proxy (see infrastructure/docker/nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
