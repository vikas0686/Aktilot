import { test, expect } from "./support/fixtures";

/**
 * Golden path for the authenticated admin app: create a project, create an
 * agent inside it, chat with the agent, and see the full pipeline detail
 * (tool steps, retrieved chunks) — this page is allowed to show it, unlike
 * the public share-link page (see public-chat.spec.ts).
 */

test("create project -> create agent -> chat -> see pipeline detail", async ({
  page,
  mock,
}) => {
  // `mock` isn't used directly here (the golden path creates state through
  // the UI), but it must still be destructured to install the route
  // interceptor for this test — see support/fixtures.ts.
  void mock;
  await page.goto("/");

  // The sidebar duplicates several of these (its own "New Project" icon
  // button, a flat project list, a per-agent nav list) so interactions and
  // text assertions for the primary content are scoped to <main> throughout.
  const main = page.getByRole("main");

  // ── Create project ───────────────────────────────────────────────────────
  await main.getByRole("button", { name: "New Project" }).click();
  await page.getByPlaceholder("My Project").fill("Acme Handbook");
  await page.getByRole("button", { name: "Create" }).click();

  const projectCard = main.getByText("Acme Handbook");
  await expect(projectCard).toBeVisible();
  await projectCard.click();
  await expect(page).toHaveURL(/\/projects\/[^/]+$/);

  // ── Switch to the Agents tab via the sidebar ────────────────────────────
  await page.getByRole("link", { name: "Agents" }).click();
  await expect(page).toHaveURL(/\/projects\/[^/]+\/agents$/);

  // ── Create agent ─────────────────────────────────────────────────────────
  await main.getByRole("button", { name: "New Agent" }).click();
  await page.getByPlaceholder("Support Bot").fill("Support Agent");
  await page.getByRole("button", { name: "Create" }).click();

  await expect(main.getByText("Support Agent")).toBeVisible();

  // ── Open chat and send a message ────────────────────────────────────────
  await main.getByRole("button", { name: "Open Chat" }).click();
  await expect(page).toHaveURL(/\/chat\/[^/]+$/);

  const input = page.getByPlaceholder(/^Message Support Agent/);
  await expect(input).toBeVisible();
  await input.fill("What is our refund policy?");
  await input.press("Enter");

  await expect(page.getByText("Mock answer to: What is our refund policy?")).toBeVisible();

  // The admin page IS allowed to show pipeline detail.
  const workflowToggle = page.getByText("View pipeline");
  await expect(workflowToggle).toBeVisible();
  await workflowToggle.click();
  await expect(page.getByText("handbook.pdf")).toBeVisible();
  await expect(page.getByText("Extract Keywords")).toBeVisible();

  // Reloading re-fetches history from the (mock) DB rather than local state.
  // (Asserting on the answer text specifically, not the bare question, since
  // the session panel also renders the question as that session's title.)
  await page.reload();
  await expect(
    page.getByText("Mock answer to: What is our refund policy?")
  ).toBeVisible();
});

test("chat input is disabled and shows a typing indicator while a reply is pending", async ({
  page,
  mock,
}) => {
  const project = mock.seedProject({ name: "P" });
  const agent = mock.seedAgent(project.id, { name: "Agent" });

  // Held open until we've asserted the pending UI, then released so the mock's
  // already-registered "**/api/**" handler (via route.fallback()) fulfills it.
  let releaseChat!: () => void;
  const chatGate = new Promise<void>((resolve) => (releaseChat = resolve));

  await page.goto(`/projects/${project.id}/agents/${agent.id}/chat`);
  await expect(page).toHaveURL(/\/chat\/[^/]+$/);

  const input = page.getByPlaceholder(/^Message Agent/);
  await input.fill("Hello?");

  // Block the network response so we can assert the pending UI deterministically.
  await page.route("**/api/agents/**/chat", async (route) => {
    await chatGate;
    await route.fallback();
  });

  await input.press("Enter");

  await expect(input).toBeDisabled();
  await expect(page.locator(".animate-typing-bounce").first()).toBeVisible();

  releaseChat();
  await expect(page.getByText(/Mock answer to: Hello\?/)).toBeVisible();
  await expect(input).toBeEnabled();
});
