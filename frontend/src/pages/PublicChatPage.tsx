import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { isAxiosError } from "axios";
import { Bot, Layers, Moon, Send, Sun } from "lucide-react";
import {
  usePublicAgent,
  usePublicSessions,
  useCreatePublicSession,
  usePublicSessionMessages,
  useSendPublicMessage,
} from "@/hooks/useApi";
import { useDarkMode } from "@/hooks/useDarkMode";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { AktilotIcon } from "@/components/AktilotIcon";
import { PublicChatSessionsPanel } from "@/components/PublicChatSessionsPanel";
import {
  AssistantAvatar,
  AssistantBubble,
  TypingDots,
  UserBubble,
} from "@/components/chat/ChatMessageParts";
import { cn } from "@/lib/utils";

type LocalMessage = {
  role: "user" | "assistant";
  content: string;
};

const DEFAULT_ERROR_MESSAGE = "Something went wrong. Please try again.";

function extractErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return DEFAULT_ERROR_MESSAGE;
}

// ── Invalid / revoked link state ──────────────────────────────────────────────

function InvalidLinkScreen() {
  return (
    <div className="flex h-screen items-center justify-center bg-background px-4">
      <EmptyState
        icon={Bot}
        title="This link isn't available"
        description="It may have been revoked or never existed. Ask whoever shared it with you for a fresh link."
      />
    </div>
  );
}

function RetryableErrorScreen({
  title = "Couldn't start a chat",
  description = "Something went wrong setting up your conversation.",
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-screen items-center justify-center bg-background px-4">
      <EmptyState
        icon={Bot}
        title={title}
        description={description}
        action={
          <button
            onClick={onRetry}
            className="text-sm font-medium text-primary hover:underline"
          >
            Try again
          </button>
        }
      />
    </div>
  );
}

function isNotFoundError(error: unknown): boolean {
  return (
    isAxiosError(error) &&
    (error.response?.status === 404 || error.response?.status === 410)
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function PublicChatPage() {
  const { slug, sessionId } = useParams<{ slug: string; sessionId?: string }>();
  const navigate = useNavigate();
  const { dark, toggle } = useDarkMode();

  const {
    data: agent,
    isError: agentError,
    error: agentErrorObj,
    isLoading: agentLoading,
    refetch: refetchAgent,
  } = usePublicAgent(slug!);
  const { data: sessions, isLoading: sessionsLoading } = usePublicSessions(slug!);
  const createSession = useCreatePublicSession(slug!);
  const { data: history, isLoading: historyLoading } = usePublicSessionMessages(
    slug!,
    sessionId
  );
  const send = useSendPublicMessage(slug!);

  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState("");
  const [initError, setInitError] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const historyLoaded = useRef(false);
  const resolvingSession = useRef(false);

  // No session in the URL: land on the most recently updated one, or create
  // a fresh one if this visitor has no chats with this agent yet.
  useEffect(() => {
    if (
      !agent ||
      sessionId ||
      sessionsLoading ||
      !sessions ||
      resolvingSession.current ||
      initError
    )
      return;

    if (sessions.length > 0) {
      navigate(`/share/${slug}/${sessions[0].id}`, { replace: true });
    } else {
      resolvingSession.current = true;
      createSession.mutate(undefined, {
        onSuccess: (session) => {
          navigate(`/share/${slug}/${session.id}`, { replace: true });
        },
        onError: () => {
          setInitError(true);
        },
        onSettled: () => {
          resolvingSession.current = false;
        },
      });
    }
  }, [
    agent,
    sessionId,
    sessionsLoading,
    sessions,
    slug,
    navigate,
    createSession,
    initError,
  ]);

  // Reset everything when switching to a different session
  useEffect(() => {
    historyLoaded.current = false;
    setLocalMessages([]);
    setInput("");
  }, [sessionId]);

  // Seed from DB history once per session
  useEffect(() => {
    if (history && !historyLoaded.current) {
      historyLoaded.current = true;
      setLocalMessages(history.map((m) => ({ role: m.role, content: m.content })));
    }
  }, [history]);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [localMessages, send.isPending]);

  const handleSend = () => {
    const q = input.trim();
    if (!q || send.isPending || !sessionId) return;
    setInput("");
    setLocalMessages((prev) => [...prev, { role: "user", content: q }]);

    send.mutate(
      { sessionId, question: q },
      {
        onSuccess: (data) => {
          setLocalMessages((prev) => [
            ...prev,
            { role: "assistant", content: data.answer },
          ]);
        },
        onError: (error) => {
          setLocalMessages((prev) => [
            ...prev,
            { role: "assistant", content: extractErrorMessage(error) },
          ]);
        },
      }
    );
  };

  if (agentLoading) {
    return (
      <div className="flex h-screen flex-col bg-background">
        <div className="mx-auto w-full max-w-3xl flex-1 px-4 pt-6">
          <Skeleton className="h-10 w-2/3 rounded-xl" />
        </div>
      </div>
    );
  }

  if (agentError && !isNotFoundError(agentErrorObj)) {
    return (
      <RetryableErrorScreen
        title="Couldn't load this chat"
        description="Something went wrong loading this agent."
        onRetry={() => refetchAgent()}
      />
    );
  }

  if (agentError || !agent) {
    return <InvalidLinkScreen />;
  }

  if (initError) {
    return <RetryableErrorScreen onRetry={() => setInitError(false)} />;
  }

  const isResolvingSession = !sessionId;
  const isLoading = isResolvingSession || historyLoading;
  const isEmpty = !isLoading && localMessages.length === 0 && !send.isPending;

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <header className="shrink-0 z-40 border-b border-border bg-card/80 backdrop-blur-md px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <AktilotIcon size={26} />
          <span className="font-semibold tracking-tight">Aktilot</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label="Toggle theme"
          className="rounded-full text-muted-foreground hover:text-foreground"
        >
          {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-auto">
            <div className="mx-auto max-w-3xl px-4 pb-8 pt-6">
              <div className="mb-8 flex items-center gap-3 border-b border-border pb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary/15 to-accent/15">
                  <Bot className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h1 className="font-semibold leading-tight tracking-tight">
                    {agent.name}
                  </h1>
                  {agent.description && (
                    <p className="text-sm text-muted-foreground">{agent.description}</p>
                  )}
                </div>
              </div>

              {isLoading ? (
                <div className="space-y-6">
                  <Skeleton className="ml-auto h-9 w-2/5 rounded-2xl" />
                  <div className="flex items-start gap-3">
                    <Skeleton className="h-8 w-8 shrink-0 rounded-full" />
                    <Skeleton className="h-16 flex-1 rounded-xl" />
                  </div>
                </div>
              ) : (
                <div className="space-y-8">
                  {isEmpty && (
                    <EmptyState
                      icon={Layers}
                      title={`${agent.name} is ready`}
                      description="Ask a question to get started."
                    />
                  )}

                  {localMessages.map((m, i) =>
                    m.role === "user" ? (
                      <UserBubble key={i} content={m.content} />
                    ) : (
                      <AssistantBubble key={i} content={m.content} />
                    )
                  )}

                  {send.isPending && (
                    <div className="flex items-start gap-3">
                      <AssistantAvatar />
                      <div className="flex items-center rounded-2xl rounded-bl-md bg-muted px-4 py-3 text-muted-foreground">
                        <TypingDots />
                      </div>
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-border px-4 py-4">
            <div className="mx-auto flex max-w-3xl gap-3">
              <input
                className={cn(
                  "flex-1 rounded-2xl border border-border bg-background px-4 py-3 text-sm",
                  "placeholder:text-muted-foreground",
                  "focus:outline-none focus:ring-2 focus:ring-primary/40",
                  "disabled:cursor-not-allowed disabled:opacity-50"
                )}
                placeholder={`Message ${agent.name}…`}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                disabled={send.isPending || isLoading}
                autoFocus
              />
              <Button
                onClick={handleSend}
                disabled={send.isPending || !input.trim() || isLoading}
                size="icon"
                className="h-11 w-11 rounded-2xl shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        <PublicChatSessionsPanel slug={slug!} activeSessionId={sessionId} />
      </div>
    </div>
  );
}
