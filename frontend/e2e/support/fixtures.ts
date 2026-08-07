import { test as base } from "@playwright/test";
import { ApiMock } from "./mockApi";

export const test = base.extend<{ mock: ApiMock }>({
  // Every test must destructure `mock` (even if unused) so this runs and the
  // route interceptor gets installed — otherwise the test silently hits the
  // real (nonexistent) network instead of failing loudly.
  mock: async ({ page }, use) => {
    const mock = new ApiMock();
    await mock.install(page);
    
    // Pre-dismiss the welcome modal for all tests to avoid blocking UI interactions.
    // Tests that specifically want to test onboarding should clear this in their setup.
    await page.addInitScript(() => {
      window.localStorage.setItem("aktilot_welcome_seen", "true");
    });
    
    await use(mock);
  },
});

export { expect } from "@playwright/test";
