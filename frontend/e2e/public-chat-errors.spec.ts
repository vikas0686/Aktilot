import { test, expect } from "./support/fixtures";

test("an unknown/revoked share slug shows the invalid-link screen", async ({
  page,
  mock,
}) => {
  // Must still destructure `mock` to install the route interceptor for this
  // test, even though no custom state is seeded — see support/fixtures.ts.
  void mock;
  await page.goto("/share/does-not-exist");
  await expect(page.getByText("This link isn't available")).toBeVisible();
  await expect(
    page.getByText(/may have been revoked or never existed/)
  ).toBeVisible();
});

test("a transient error loading the agent shows a retryable error with a working retry", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "P" });
  const agent = mock.seedAgent(project.id, { name: "Helper", share_slug: "flaky-slug" });

  let attempt = 0;
  await page.route(`**/api/public/agents/${agent.share_slug}`, async (route) => {
    attempt += 1;
    if (attempt === 1) {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "boom" }),
      });
    }
    return route.fallback();
  });

  await page.goto(`/share/${agent.share_slug}`);
  await expect(page.getByText("Couldn't load this chat")).toBeVisible();

  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Helper" })).toBeVisible();
  await expect(page.getByText("Couldn't load this chat")).toHaveCount(0);
});

test("a 429 from the chat endpoint renders the rate-limit message inline, not a hard error", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "P" });
  const agent = mock.seedAgent(project.id, { name: "Helper", share_slug: "capped-slug" });

  mock.scriptPublicChat({
    status: 429,
    detail: "You've reached the message limit for this chat. Please try again in a bit.",
  });

  await page.goto(`/share/${agent.share_slug}`);
  const input = page.getByPlaceholder(/^Message Helper/);
  await input.fill("One more question");
  await input.press("Enter");

  await expect(
    page.getByText("You've reached the message limit for this chat. Please try again in a bit.")
  ).toBeVisible();
  // The composer must remain usable after an error — this isn't a fatal state.
  await expect(input).toBeEnabled();
});

test("session creation failing shows a retryable error distinct from an invalid link", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "P" });
  const agent = mock.seedAgent(project.id, { name: "Helper", share_slug: "init-fail-slug" });

  let attempt = 0;
  await page.route(`**/api/public/agents/${agent.share_slug}/sessions`, (route) => {
    if (route.request().method() === "POST") {
      attempt += 1;
      if (attempt === 1) {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "boom" }),
        });
      }
      return route.fallback();
    }
    return route.fallback();
  });

  await page.goto(`/share/${agent.share_slug}`);
  await expect(page.getByText("Couldn't start a chat")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();

  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByPlaceholder(/^Message Helper/)).toBeVisible();
});
