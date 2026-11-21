import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    // GitHub Pages отдаёт сайт по подпути /<имя-репозитория>/.
    // Локально и на своём домене base остаётся "/".
    base: env.VITE_BASE_PATH || "/",
    plugins: [react(), tailwindcss()],
    server: {
      proxy: { "/api": env.SYNONYX_API_TARGET || "http://localhost:8000" },
    },
  };
});
