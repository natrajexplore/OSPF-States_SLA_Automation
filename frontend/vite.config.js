import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` proxies the API to a backend on this machine (or set VITE_API=http://<eve-vm>:8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_API || "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
