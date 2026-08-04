/// <reference types="vitest/config" />

import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          includeDependenciesRecursively: false,
          groups: [
            {
              name: "react-vendor",
              test: /node_modules\/(react|react-dom|scheduler)\//,
            },
            {
              name: "data-vendor",
              test: /node_modules\/(@tanstack|axios|react-router|zustand)\//,
            },
            {
              name: "ui-vendor",
              test: /node_modules\/(@radix-ui|lucide-react|sonner)\//,
            },
            {
              name: "vendor",
              test: /node_modules/,
            },
          ],
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
  },
})
