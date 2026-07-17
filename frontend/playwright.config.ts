import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run against a production build (`vite preview`) served on a
 * fixed port, with every `/api/**` call intercepted in-browser by
 * `e2e/support/mockApi.ts` — no real backend, database, or LLM involved.
 * `npm run test:e2e` builds first so `dist/` is always fresh.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // 1 retry everywhere (not just CI): there's a known cold-start race between
  // the spawned `vite preview` webServer reporting ready and the first
  // navigation, which surfaces as a "Cannot navigate to invalid URL" on the
  // very first test of a run. A retry reliably clears it since the server is
  // fully warm by then; this is an environment race, not app or test flakiness.
  retries: 1,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run preview -- --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
