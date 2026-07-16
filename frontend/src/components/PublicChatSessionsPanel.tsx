import { Link, useNavigate } from "react-router-dom";
import { Loader2, MessageSquare, Plus } from "lucide-react";
import { usePublicSessions, useCreatePublicSession } from "@/hooks/useApi";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

function formatUpdatedAt(iso: string) {
  return new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function PublicChatSessionsPanel({
  slug,
  activeSessionId,
}: {
  slug: string;
  activeSessionId?: string;
}) {
  const { data: sessions, isLoading } = usePublicSessions(slug);
  const createSession = useCreatePublicSession(slug);
  const navigate = useNavigate();

  const handleNewChat = () => {
    createSession.mutate(undefined, {
      onSuccess: (session) => {
        navigate(`/share/${slug}/${session.id}`);
      },
    });
  };

  return (
    <aside className="flex w-72 shrink-0 flex-col overflow-hidden border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Your Chats
        </span>
        <button
          onClick={handleNewChat}
          disabled={createSession.isPending}
          title="New Chat"
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
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
          <div className="space-y-1.5 px-1 py-1">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-11 w-full rounded-lg" />
            ))}
          </div>
        ) : sessions?.length === 0 ? (
          <EmptyState
            size="sm"
            icon={MessageSquare}
            title="No chats yet"
            action={
              <button
                onClick={handleNewChat}
                className="text-xs font-medium text-primary hover:underline"
              >
                Start your first chat
              </button>
            }
          />
        ) : (
          <div className="space-y-0.5">
            {sessions?.map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <Link
                  key={session.id}
                  to={`/share/${slug}/${session.id}`}
                  className={cn(
                    "relative flex items-start gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors",
                    isActive
                      ? cn(
                          "bg-primary/10 font-medium text-primary",
                          "before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-full before:bg-primary"
                        )
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
