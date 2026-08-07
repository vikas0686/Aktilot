import { useState, useCallback } from "react";

const WELCOME_SEEN_KEY = "aktilot_welcome_seen";
const GETTING_STARTED_DISMISSED_PREFIX = "aktilot_getting_started_dismissed_";

/**
 * Hook for managing onboarding-related localStorage flags.
 * Tracks whether user has seen the welcome modal and dismissed getting started cards.
 */
export function useOnboarding() {
  const [hasSeenWelcome, setHasSeenWelcome] = useState(
    () => localStorage.getItem(WELCOME_SEEN_KEY) === "true"
  );

  const markWelcomeSeen = useCallback(() => {
    localStorage.setItem(WELCOME_SEEN_KEY, "true");
    setHasSeenWelcome(true);
  }, []);

  const dismissGettingStarted = useCallback((projectId: string) => {
    localStorage.setItem(`${GETTING_STARTED_DISMISSED_PREFIX}${projectId}`, "true");
  }, []);

  const isGettingStartedDismissed = useCallback((projectId: string) => {
    return localStorage.getItem(`${GETTING_STARTED_DISMISSED_PREFIX}${projectId}`) === "true";
  }, []);

  /**
   * Determines whether to show the Getting Started card for a project.
   * Returns false if:
   * - User has dismissed it for this project
   * - User has completed the workflow (has both files and agents)
   */
  const shouldShowGettingStarted = useCallback(
    (projectId: string, hasFiles: boolean, hasAgents: boolean) => {
      // Don't show if dismissed
      if (isGettingStartedDismissed(projectId)) {
        return false;
      }
      // Don't show if workflow is complete (has both files and agents)
      if (hasFiles && hasAgents) {
        return false;
      }
      // Show for new/incomplete projects
      return true;
    },
    [isGettingStartedDismissed]
  );

  return {
    hasSeenWelcome,
    markWelcomeSeen,
    dismissGettingStarted,
    isGettingStartedDismissed,
    shouldShowGettingStarted,
  };
}
