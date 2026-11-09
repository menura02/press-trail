import { defineConfig, loadEnv } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => ({
  plugins: [tailwindcss()],
  esbuild: { jsx: "automatic" },
  server: {
    strictPort: true,
    proxy: {
      "/api": {
        target: loadEnv(mode, ".", "HABER_").HABER_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
}));
