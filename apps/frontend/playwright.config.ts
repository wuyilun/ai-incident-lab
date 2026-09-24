import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1440, height: 1080 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
  webServer: {
    command: "../../.venv/bin/python ../../scripts/dev.py",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    env: {
      LAB_DB: "data/browser-test.sqlite",
      TICK_SECONDS: "0.5",
      AGENT_POLL_SECONDS: "0.5",
    },
  },
});
