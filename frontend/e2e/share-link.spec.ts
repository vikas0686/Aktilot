import { test, expect } from "./support/fixtures";

/**
 * Share-link generation from the admin app, then the resulting public URL
 * end to end. The regression this guards is the metadata leak fixed
 * previously: the public chat page must render ONLY the answer, even if a
 * (regressed) backend response included tool_steps/retrieved_chunks.
 */

test("generate a share link and use it as an anonymous visitor", async ({ page, mock }) => {
  const project = mock.seedProject({ name: "Acme" });
  mock.seedAgent(project.id, { name: "Helper" });

  await page.goto(`/projects/${project.id}/agents`);
  await page.getByRole("button", { name: "Share agent" }).click();
  await page.getByRole("button", { name: "Generate Link" }).click();

  const shareUrlInput = page.locator('input[readonly]');
  await expect(shareUrlInput).toBeVisible();
  const shareUrl = await shareUrlInput.inputValue();
  const sharePath = new URL(shareUrl).pathname;
  expect(sharePath).toMatch(/^\/share\//);

  // Simulate the backend regressing and sending pipeline metadata to the
  // public route again — the UI must still not render it.
  mock.scriptPublicChat({
    answer: "Refunds are processed within 5 business days.",
    toolSteps: [{ name: "Extract Keywords" }],
    retrievedChunks: [
      { chunk_id: "leak1", filename: "secret-internal-doc.pdf", content: "should never render" },
    ],
  });

  // ── Visit as an anonymous visitor (fresh context = fresh cookies) ───────
  await page.context().clearCookies();
  await page.goto(sharePath);
  await expect(page).toHaveURL(new RegExp(`/share/[^/]+/[^/]+$`));
  await expect(page.getByRole("heading", { name: "Helper" })).toBeVisible();

  const input = page.getByPlaceholder(/^Message Helper/);
  await input.fill("What's the refund policy?");
  await input.press("Enter");

  await expect(
    page.getByText("Refunds are processed within 5 business days.")
  ).toBeVisible();

  // No pipeline UI at all on the public page, regardless of what the mocked
  // response contained.
  await expect(page.getByText("View pipeline")).toHaveCount(0);
  await expect(page.getByText("secret-internal-doc.pdf")).toHaveCount(0);
  await expect(page.getByText("Extract Keywords")).toHaveCount(0);

  // Reloading re-fetches from the (mock) DB — still just plain messages.
  // (Asserting on the answer, not the bare question, since the session
  // panel also renders the question as that session's title.)
  await page.reload();
  await expect(
    page.getByText("Refunds are processed within 5 business days.")
  ).toBeVisible();
  await expect(page.getByText("secret-internal-doc.pdf")).toHaveCount(0);
});

test("revoking a share link stops it from working for the admin (regenerate/revoke UI)", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "Acme" });
  mock.seedAgent(project.id, { name: "Helper" });

  await page.goto(`/projects/${project.id}/agents`);
  await page.getByRole("button", { name: "Share agent" }).click();
  await page.getByRole("button", { name: "Generate Link" }).click();

  const shareUrlInput = page.locator('input[readonly]');
  await expect(shareUrlInput).toBeVisible();
  const shareUrl = await shareUrlInput.inputValue();
  const sharePath = new URL(shareUrl).pathname;

  await page.getByRole("button", { name: "Revoke" }).click();
  await expect(page.locator('input[readonly]')).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Generate Link" })).toBeVisible();

  // The revoked link must actually stop working, not just disappear from
  // the admin UI — visiting it now must show the invalid-link state.
  await page.goto(sharePath);
  await expect(page.getByText("This link isn't available")).toBeVisible();
});
