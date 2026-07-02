import { Link, useNavigate } from "react-router-dom";
import { Loader2, MessageSquare, Plus } from "lucide-react";
import { useAgentSessions, useCreateChatSession } from "@/hooks/useApi";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

function formatUpdatedAt(iso: string) {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ChatSessionsPanel({
  projectId,
  agentId,
  activeSessionId,
}: {
  projectId: string;
  agentId: string;
  activeSessionId?: string;
}) {
  const { data: sessions, isLoading } = useAgentSessions(agentId);
  const createSession = useCreateChatSession(agentId);
  const navigate = useNavigate();

  const handleNewChat = () => {
    createSession.mutate(undefined, {
      onSuccess: (session) => {
        navigate(`/projects/${projectId}/agents/${agentId}/chat/${session.id}`);
      },
    });
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col overflow-hidden border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Chats
        </span>
        <button
          onClick={handleNewChat}
          disabled={createSession.isPending}
          title="New Chat"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          {createSession.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="flex justify-center py-6">
            <Spinner className="h-4 w-4" />
          </div>
        ) : sessions?.length === 0 ? (
          <div className="px-2 py-4 text-center">
            <p className="text-xs text-muted-foreground">No chats yet.</p>
            <button
              onClick={handleNewChat}
              className="mt-1.5 text-xs text-primary hover:underline"
            >
              Start your first chat
            </button>
          </div>
        ) : (
          <div className="space-y-0.5">
            {sessions?.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <Link
                  key={session.id}
                  to={`/projects/${projectId}/agents/${agentId}/chat/${session.id}`}
                  className={cn(
                    "flex items-start gap-2 rounded px-2 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-primary/10 font-medium text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate">{session.title ?? "New chat"}</div>
                    <div className="text-xs text-muted-foreground/70">
                      {formatUpdatedAt(session.updated_at)}
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
