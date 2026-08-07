import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { WelcomeModal } from "@/components/WelcomeModal";

describe("WelcomeModal", () => {
  it("renders when open is true", () => {
    render(<WelcomeModal open={true} onClose={vi.fn()} />);
    
    expect(screen.getByText("Welcome to Aktilot")).toBeInTheDocument();
    expect(screen.getByText("Chat with your documents. On your infrastructure.")).toBeInTheDocument();
  });

  it("does not render when open is false", () => {
    render(<WelcomeModal open={false} onClose={vi.fn()} />);
    
    expect(screen.queryByText("Welcome to Aktilot")).not.toBeInTheDocument();
  });

  it("displays all onboarding steps", () => {
    render(<WelcomeModal open={true} onClose={vi.fn()} />);
    
    expect(screen.getByText("Upload documents")).toBeInTheDocument();
    expect(screen.getByText("Create an agent")).toBeInTheDocument();
    expect(screen.getByText("Start chatting")).toBeInTheDocument();
  });

  it("calls onClose when Get Started button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    
    render(<WelcomeModal open={true} onClose={onClose} />);
    
    await user.click(screen.getByRole("button", { name: "Get Started" }));
    
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    
    render(<WelcomeModal open={true} onClose={onClose} />);
    
    await user.keyboard("{Escape}");
    
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when clicking outside the dialog (backdrop)", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    
    render(<WelcomeModal open={true} onClose={onClose} />);
    
    // The dialog backdrop is the overlay element
    // Radix Dialog uses data-state="open" on the overlay
    const overlay = document.querySelector("[data-state='open']");
    expect(overlay).toBeTruthy();
    
    // Click on the overlay/backdrop (outside the dialog content)
    await user.click(overlay!);
    
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
