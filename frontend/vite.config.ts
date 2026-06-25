import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

// Dev server proxies API calls to the FastAPI backend so the app can use
// same-origin relative URLs in both dev and the built single-process deployment.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      "/api": `http://127.0.0.1:${process.env.RSS_READER_PORT || 8000}`,
    },
  },
  build: {
    outDir: "dist",
  },
});
