import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import { ProjectsPage } from "@/pages/ProjectsPage";
import { ProjectDetailPage } from "@/pages/ProjectDetailPage";
import { ProjectAgentsPage } from "@/pages/ProjectAgentsPage";
import { AgentChatPage } from "@/pages/AgentChatPage";
import { PublicChatPage } from "@/pages/PublicChatPage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 10_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Standalone public chat: no AppShell, no nav to the rest of the app. */}
          <Route path="/share/:slug" element={<PublicChatPage />} />
          <Route path="/share/:slug/:sessionId" element={<PublicChatPage />} />

          <Route
            path="*"
            element={
              <AppShell>
                <Routes>
                  <Route path="/" element={<ProjectsPage />} />
                  <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
                  <Route
                    path="/projects/:projectId/agents"
                    element={<ProjectAgentsPage />}
                  />
                  <Route
                    path="/projects/:projectId/agents/:agentId/chat"
                    element={<AgentChatPage />}
                  />
                  <Route
                    path="/projects/:projectId/agents/:agentId/chat/:sessionId"
                    element={<AgentChatPage />}
                  />
                </Routes>
              </AppShell>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
