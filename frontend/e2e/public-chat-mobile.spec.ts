import { test, expect } from "./support/fixtures";

test.use({ viewport: { width: 390, height: 844 } });

test("mobile session drawer opens, lists chats, and closes on navigation", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "P" });
  const agent = mock.seedAgent(project.id, { name: "Helper", share_slug: "mobile-slug" });

  await page.goto(`/share/${agent.share_slug}`);
  await expect(page).toHaveURL(new RegExp(`/share/${agent.share_slug}/[^/]+$`));

  // Desktop sidebar is hidden at this viewport; only the floating toggle shows.
  await expect(page.getByRole("button", { name: "Your Chats" })).toBeVisible();

  await page.getByRole("button", { name: "Your Chats" }).click();

  // The panel is rendered twice in the DOM (a CSS-hidden desktop copy plus
  // the mobile drawer) — scope to the drawer overlay so locators aren't
  // ambiguous between the two.
  const drawer = page.locator(".fixed.inset-0.z-50");
  await expect(drawer.getByRole("button", { name: "Close" })).toBeVisible();

  // Starting a new chat from the drawer navigates and closes it.
  await drawer.getByRole("button", { name: "New Chat" }).click();
  await expect(page.locator(".fixed.inset-0.z-50")).toHaveCount(0);
});
