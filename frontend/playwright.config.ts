import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run the real app: the backend (with Postgres) must already be running
 * on :8000 with an operator account, see .github/workflows/ci.yml. Playwright starts the
 * Vite dev server itself (or reuses one already on :5173). The test leaves the reactor
 * scrammed, so run it against a freshly started backend (as CI does).
 *
 *   E2E_USERNAME / E2E_PASSWORD   operator credentials (required)
 *   PLAYWRIGHT_CHROME_PATH        use an installed Chrome instead of Playwright's Chromium
 */
const chromePath = process.env.PLAYWRIGHT_CHROME_PATH;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
        launchOptions: chromePath ? { executablePath: chromePath } : {},
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
