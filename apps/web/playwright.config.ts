import path from "node:path"
import { fileURLToPath } from "node:url"

import { defineConfig, devices } from "@playwright/test"

const directory = path.dirname(fileURLToPath(import.meta.url))
const workspace = path.resolve(directory, "../..")

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "pnpm --filter api dev",
      cwd: workspace,
      env: {
        ...process.env,
        GPT_AUTO_DATABASE_URL:
          "sqlite+pysqlite:////tmp/gpt-auto-register-playwright.db",
      },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "pnpm --filter web dev",
      cwd: workspace,
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
