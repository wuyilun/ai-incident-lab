import { defineConfig } from "@playwright/test";
const frontendPort = process.env.LAB_FRONTEND_PORT ?? "5173";
const controlPort = process.env.LAB_CONTROL_PORT ?? "8000";
const agentPort = process.env.LAB_AGENT_PORT ?? "8001";
const baseURL = `http://127.0.0.1:${frontendPort}`;
export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL,
    viewport: { width: 1440, height: 1080 },
    screenshot: "only-on-failure",
    // Traces capture registration responses containing one-time credentials.
    trace: "off",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
    },
  },
  webServer: {
    command: "../../.venv/bin/python ../../scripts/dev.py",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    gracefulShutdown: { signal: "SIGTERM", timeout: 15000 },
    env: {
      LAB_DB: process.env.LAB_DB ?? "data/browser-test.sqlite",
      LAB_CONTROL_PORT: controlPort,
      LAB_AGENT_PORT: agentPort,
      LAB_FRONTEND_PORT: frontendPort,
      TICK_SECONDS: "0.5",
      AGENT_POLL_SECONDS: "0.5",
    },
  },
});
