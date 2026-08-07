import { test as base, expect } from "@playwright/test";
import { ApiMock } from "./support/mockApi";

/**
 * Custom test fixture for onboarding tests that does NOT pre-dismiss the welcome modal.
 * This allows testing the welcome modal flow specifically.
 */
const test = base.extend<{ mock: ApiMock }>({
  mock: async ({ page }, use) => {
    const mock = new ApiMock();
    await mock.install(page);
    // Note: We do NOT set aktilot_welcome_seen here like the regular fixtures do,
    // so the welcome modal will appear as expected for first-time users.
    await use(mock);
  },
});

/**
 * Tests the onboarding UX improvements:
 * - Welcome modal on first visit
 * - Getting Started card inside projects
 * - Smart default system prompt in agent form
 */

test.describe("Onboarding flow", () => {
  test("welcome modal appears on first visit and dismisses permanently", async ({
    page,
    mock,
  }) => {
    void mock;

    // Clear localStorage to simulate fresh user (only on first load)
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    // Welcome modal should be visible
    const modal = page.getByRole("dialog");
    await expect(modal).toBeVisible();
    await expect(page.getByText("Welcome to Aktilot")).toBeVisible();
    await expect(page.getByText("Chat with your documents. On your infrastructure.")).toBeVisible();

    // Verify the 3 steps are shown
    await expect(page.getByText("Upload documents")).toBeVisible();
    await expect(page.getByText("Create an agent")).toBeVisible();
    await expect(page.getByText("Start chatting")).toBeVisible();

    // Click "Get Started" to dismiss
    await page.getByRole("button", { name: "Get Started" }).click();

    // Modal should be gone
    await expect(modal).not.toBeVisible();

    // Reload page - modal should NOT reappear (localStorage persists)
    await page.reload();
    await expect(page.getByText("Welcome to Aktilot")).not.toBeVisible();
  });

  test("getting started card appears in new projects and tracks progress", async ({
    page,
    mock,
  }) => {
    void mock;

    // Clear localStorage and reload
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    // First dismiss the welcome modal
    await page.getByRole("button", { name: "Get Started" }).click();

    const main = page.getByRole("main");

    // Create a new project
    await main.getByRole("button", { name: "New Project" }).click();
    await page.getByPlaceholder("My Project").fill("Test Project");
    await page.getByRole("button", { name: "Create" }).click();

    // Click on the project to enter it
    await main.getByText("Test Project").click();
    await expect(page).toHaveURL(/\/projects\/[^/]+$/);

    // Getting Started card should be visible
    await expect(page.getByText("Getting Started")).toBeVisible();
    await expect(page.getByText("0 of 2 steps completed")).toBeVisible();

    // Verify the steps are shown
    await expect(page.getByText("Upload documents").first()).toBeVisible();
    await expect(page.getByText("Create an agent").first()).toBeVisible();
    await expect(page.getByText("Start chatting").first()).toBeVisible();
  });

  test("getting started card can be dismissed", async ({ page, mock }) => {
    void mock;

    // Clear localStorage and reload
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    // Dismiss welcome modal and create a project
    await page.getByRole("button", { name: "Get Started" }).click();

    const main = page.getByRole("main");
    await main.getByRole("button", { name: "New Project" }).click();
    await page.getByPlaceholder("My Project").fill("Dismissable Project");
    await page.getByRole("button", { name: "Create" }).click();
    await main.getByText("Dismissable Project").click();

    // Getting Started card should be visible
    await expect(page.getByText("Getting Started")).toBeVisible();

    // Click the dismiss button (X)
    await page.getByTitle("Dismiss").click();

    // Card should be gone
    await expect(page.getByText("Getting Started")).not.toBeVisible();

    // Reload - card should still be gone (persisted dismissal)
    await page.reload();
    await expect(page.getByText("Getting Started")).not.toBeVisible();
  });

  test("agent form has smart default system prompt", async ({ page, mock }) => {
    void mock;

    // Clear localStorage and reload
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    // Dismiss welcome modal and create a project
    await page.getByRole("button", { name: "Get Started" }).click();

    const main = page.getByRole("main");
    await main.getByRole("button", { name: "New Project" }).click();
    await page.getByPlaceholder("My Project").fill("Agent Test Project");
    await page.getByRole("button", { name: "Create" }).click();
    await main.getByText("Agent Test Project").click();

    // Navigate to agents
    await page.getByRole("link", { name: "Agents" }).click();
    await expect(page).toHaveURL(/\/projects\/[^/]+\/agents$/);

    // Open new agent form
    await main.getByRole("button", { name: "New Agent" }).click();

    // Verify the form has the default system prompt pre-filled
    const systemPromptTextarea = page.locator('textarea');
    await expect(systemPromptTextarea).toHaveValue(/You are a helpful assistant/);
    await expect(systemPromptTextarea).toHaveValue(/Answer questions based on the provided context/);
    await expect(systemPromptTextarea).toHaveValue(/If the answer isn't in the context, say so clearly/);

    // Verify the helpful tip is shown for new agents
    await expect(page.getByText("Tip: This default works well for most Q&A use cases")).toBeVisible();

    // Verify improved placeholder for name field
    const nameInput = page.getByPlaceholder("e.g., Support Bot, Research Assistant");
    await expect(nameInput).toBeVisible();
  });

  test("empty states show contextual guidance", async ({ page, mock }) => {
    void mock;

    // Clear localStorage and reload
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.reload();

    // Dismiss welcome modal and create a project
    await page.getByRole("button", { name: "Get Started" }).click();

    const main = page.getByRole("main");
    await main.getByRole("button", { name: "New Project" }).click();
    await page.getByPlaceholder("My Project").fill("Empty State Project");
    await page.getByRole("button", { name: "Create" }).click();
    await main.getByText("Empty State Project").click();

    // Navigate to files
    await page.getByRole("link", { name: "Knowledge Base" }).click();
    await page.getByText("Upload files").click();

    // Check FilesTab empty state has the new subtitle
    await expect(page.getByText("Your agent will use these documents to answer questions accurately")).toBeVisible();

    // Navigate to agents
    await page.getByRole("link", { name: "Agents" }).click();

    // Check AgentsTab empty state has the new description and subtitle
    await expect(page.getByText("Create an agent to chat with your documents.")).toBeVisible();
    await expect(page.getByText("Each agent has its own personality and retrieval settings.")).toBeVisible();
  });
});
