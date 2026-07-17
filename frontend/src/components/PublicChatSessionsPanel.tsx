import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, MessageSquare, Plus, X } from "lucide-react";
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
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleNewChat = () => {
    createSession.mutate(undefined, {
      onSuccess: (session) => {
        navigate(`/share/${slug}/${session.id}`);
        setMobileOpen(false);
      },
    });
  };

  const body = (onNavigate?: () => void) => (
    <>
      <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Your Chats
        </span>
        <div className="flex items-center gap-1">
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
          {onNavigate && (
            <button
              onClick={() => setMobileOpen(false)}
              title="Close"
              className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground md:hidden"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
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
                disabled={createSession.isPending}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
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
                  onClick={onNavigate}
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
    </>
  );

  return (
    <>
      {/* Desktop: static sidebar */}
      <aside className="hidden w-72 shrink-0 flex-col overflow-hidden border-l border-border bg-card md:flex">
        {body()}
      </aside>

      {/* Mobile: floating toggle + slide-in drawer, so session nav stays
          reachable without permanently eating into the chat/input width. */}
      <button
        onClick={() => setMobileOpen(true)}
        title="Your Chats"
        className="fixed bottom-4 right-4 z-40 flex h-11 w-11 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-lg md:hidden"
      >
        <MessageSquare className="h-4 w-4" />
      </button>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col overflow-hidden border-l border-border bg-card shadow-xl">
            {body(() => setMobileOpen(false))}
          </aside>
        </div>
      )}
    </>
  );
}
