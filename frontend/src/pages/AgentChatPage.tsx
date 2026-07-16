import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Bot, Layers, Send } from "lucide-react";
import {
  useAgent,
  useAgentSessions,
  useCreateChatSession,
  useSessionMessages,
  useSendAgentMessage,
} from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ChatSessionsPanel } from "@/components/ChatSessionsPanel";
import {
  AssistantAvatar,
  AssistantBubble,
  TypingDots,
  UserBubble,
} from "@/components/chat/ChatMessageParts";
import { cn } from "@/lib/utils";
import type { ChatResponse } from "@/types/api";

type LocalMessage = {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
};

// ── Page ──────────────────────────────────────────────────────────────────────

export function AgentChatPage() {
  const { projectId, agentId, sessionId } = useParams<{
    projectId: string;
    agentId: string;
    sessionId?: string;
  }>();
  const navigate = useNavigate();

  const { data: agent } = useAgent(agentId!);
  const { data: sessions, isLoading: sessionsLoading } = useAgentSessions(agentId!);
  const createSession = useCreateChatSession(agentId!);
  const { data: history, isLoading: historyLoading } = useSessionMessages(sessionId);
  const send = useSendAgentMessage(agentId!, sessionId);

  const [localMessages, setLocalMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const historyLoaded = useRef(false);
  const resolvingSession = useRef(false);

  // No session in the URL: land on the most recently updated one, or create
  // a fresh one if this agent has no chats yet.
  useEffect(() => {
    if (sessionId || sessionsLoading || !sessions || resolvingSession.current) return;

    if (sessions.length > 0) {
      navigate(`/projects/${projectId}/agents/${agentId}/chat/${sessions[0].id}`, {
        replace: true,
      });
    } else {
      resolvingSession.current = true;
      createSession.mutate(undefined, {
        onSuccess: (session) => {
          navigate(
            `/projects/${projectId}/agents/${agentId}/chat/${session.id}`,
            { replace: true }
          );
        },
        onSettled: () => {
          resolvingSession.current = false;
        },
      });
    }
  }, [sessionId, sessionsLoading, sessions, projectId, agentId, navigate, createSession]);

  // Reset everything when switching to a different session
  useEffect(() => {
    historyLoaded.current = false;
    setLocalMessages([]);
    setInput("");
  }, [agentId, sessionId]);

  // Seed from DB history once per session
  useEffect(() => {
    if (history && !historyLoaded.current) {
      historyLoaded.current = true;
      setLocalMessages(
        history.map((m) => ({ role: m.role, content: m.content }))
      );
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

    send.mutate(q, {
      onSuccess: (data) => {
        setLocalMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.answer, response: data },
        ]);
      },
      onError: () => {
        setLocalMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: "Something went wrong. Please try again.",
          },
        ]);
      },
    });
  };

  const isResolvingSession = !sessionId;
  const isLoading = isResolvingSession || historyLoading;
  const isEmpty = !isLoading && localMessages.length === 0 && !send.isPending;

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat thread */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-auto">
          <div className="mx-auto max-w-3xl px-4 pb-8 pt-6">
            {/* Agent header */}
            <div className="mb-8 flex items-center gap-3 border-b border-border pb-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-primary/15 to-accent/15">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="font-semibold leading-tight tracking-tight">
                  {agent?.name ?? "Loading…"}
                </h1>
                {agent?.description && (
                  <p className="text-sm text-muted-foreground">{agent.description}</p>
                )}
              </div>
            </div>

            {/* Messages */}
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
                    title={`${agent?.name ?? "Agent"} is ready`}
                    description="Ask anything about the project's documents."
                  />
                )}

                {localMessages.map((m, i) =>
                  m.role === "user" ? (
                    <UserBubble key={i} content={m.content} />
                  ) : (
                    <AssistantBubble
                      key={i}
                      content={m.content}
                      response={m.response}
                    />
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

        {/* Input bar */}
        <div className="border-t border-border px-4 py-4">
          <div className="mx-auto flex max-w-3xl gap-3">
            <input
              className={cn(
                "flex-1 rounded-2xl border border-border bg-background px-4 py-3 text-sm",
                "placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-2 focus:ring-primary/40",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
              placeholder={`Message ${agent?.name ?? "agent"}…`}
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

      {/* Chat history panel */}
      <ChatSessionsPanel
        projectId={projectId!}
        agentId={agentId!}
        activeSessionId={sessionId}
      />
    </div>
  );
}
