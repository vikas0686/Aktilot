import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useOnboarding } from "@/hooks/useOnboarding";

describe("useOnboarding", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  describe("hasSeenWelcome", () => {
    it("returns false when localStorage is empty", () => {
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.hasSeenWelcome).toBe(false);
    });

    it("returns true when welcome has been seen", () => {
      localStorage.setItem("aktilot_welcome_seen", "true");
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.hasSeenWelcome).toBe(true);
    });
  });

  describe("markWelcomeSeen", () => {
    it("sets hasSeenWelcome to true and persists to localStorage", () => {
      const { result } = renderHook(() => useOnboarding());
      
      expect(result.current.hasSeenWelcome).toBe(false);
      
      act(() => {
        result.current.markWelcomeSeen();
      });
      
      expect(result.current.hasSeenWelcome).toBe(true);
      expect(localStorage.getItem("aktilot_welcome_seen")).toBe("true");
    });

    it("persists across hook re-mounts", () => {
      const { result, unmount } = renderHook(() => useOnboarding());
      
      act(() => {
        result.current.markWelcomeSeen();
      });
      
      unmount();
      
      const { result: newResult } = renderHook(() => useOnboarding());
      expect(newResult.current.hasSeenWelcome).toBe(true);
    });
  });

  describe("dismissGettingStarted", () => {
    it("persists dismissal for a specific project", () => {
      const { result } = renderHook(() => useOnboarding());
      const projectId = "test-project-123";
      
      act(() => {
        result.current.dismissGettingStarted(projectId);
      });
      
      expect(localStorage.getItem(`aktilot_getting_started_dismissed_${projectId}`)).toBe("true");
    });

    it("does not affect other projects", () => {
      const { result } = renderHook(() => useOnboarding());
      
      act(() => {
        result.current.dismissGettingStarted("project-1");
      });
      
      expect(result.current.isGettingStartedDismissed("project-1")).toBe(true);
      expect(result.current.isGettingStartedDismissed("project-2")).toBe(false);
    });
  });

  describe("shouldShowGettingStarted", () => {
    it("returns true for new projects with no files and no agents", () => {
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.shouldShowGettingStarted("new-project", false, false)).toBe(true);
    });

    it("returns true when project has files but no agents", () => {
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.shouldShowGettingStarted("project", true, false)).toBe(true);
    });

    it("returns true when project has agents but no files", () => {
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.shouldShowGettingStarted("project", false, true)).toBe(true);
    });

    it("returns false when project has both files and agents", () => {
      const { result } = renderHook(() => useOnboarding());
      expect(result.current.shouldShowGettingStarted("project", true, true)).toBe(false);
    });

    it("returns false when user has dismissed it for this project", () => {
      const { result } = renderHook(() => useOnboarding());
      const projectId = "dismissed-project";
      
      act(() => {
        result.current.dismissGettingStarted(projectId);
      });
      
      expect(result.current.shouldShowGettingStarted(projectId, false, false)).toBe(false);
    });

    it("dismissal takes precedence over completion state", () => {
      const { result } = renderHook(() => useOnboarding());
      const projectId = "project";
      
      act(() => {
        result.current.dismissGettingStarted(projectId);
      });
      
      // Even with incomplete state, should return false because dismissed
      expect(result.current.shouldShowGettingStarted(projectId, false, false)).toBe(false);
    });
  });
});
