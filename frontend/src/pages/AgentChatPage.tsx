import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Clock,
  Send,
  CheckCircle,
} from "lucide-react";
import {
  useAgent,
  useAgentSessions,
  useCreateChatSession,
  useSessionMessages,
  useSendAgentMessage,
} from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { ChatSessionsPanel } from "@/components/ChatSessionsPanel";
import { cn } from "@/lib/utils";
import type { ChatResponse, RetrievedChunk, ToolStep } from "@/types/api";

type LocalMessage = {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
};

// ── Pipeline step ─────────────────────────────────────────────────────────────

function ToolStepRow({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-md border border-border text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 transition-colors hover:bg-muted"
      >
        <CheckCircle className="h-3.5 w-3.5 shrink-0 text-green-500" />
        <span className="flex-1 text-left font-medium">{step.name}</span>
        <span className="text-muted-foreground">{step.duration_ms.toFixed(0)}ms</span>
        {open ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        )}
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-border bg-muted/30 px-3 pb-3 pt-2">
          <p className="text-muted-foreground">
            <span className="font-medium">In:</span> {step.input_summary}
          </p>
          <p className="text-muted-foreground">
            <span className="font-medium">Out:</span> {step.output_summary}
          </p>
          <p className="flex items-center gap-1 text-muted-foreground">
            <Clock className="h-3 w-3" />
            {new Date(step.start_time).toLocaleTimeString()} →{" "}
            {new Date(step.end_time).toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Source chunk card with score breakdown ────────────────────────────────────

function ChunkCard({ chunk, index }: { chunk: RetrievedChunk; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-md border border-border text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 transition-colors hover:bg-muted"
      >
        {/* Filename + kw hits badge */}
        <div className="flex flex-1 min-w-0 items-center gap-2">
          <span className="truncate font-medium">
            {index + 1}. {chunk.filename} · #{chunk.chunk_index}
          </span>
          {chunk.kw_hits > 0 && (
            <span className="shrink-0 rounded-full bg-amber-100 px-1.5 py-0.5 font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
              {chunk.kw_hits} kw
            </span>
          )}
        </div>
        {/* Hybrid score */}
        <span className="shrink-0 font-semibold text-primary">
          {(chunk.score * 100).toFixed(0)}%
        </span>
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
      </button>

      {open && (
        <div className="space-y-2.5 border-t border-border bg-muted/30 px-3 pb-3 pt-2">
          {/* Score breakdown */}
          <div className="flex gap-4 text-muted-foreground">
            <span>
              Vec:{" "}
              <strong className="text-foreground">
                {(chunk.vec_score * 100).toFixed(0)}%
              </strong>
            </span>
            <span>
              BM25:{" "}
              <strong className="text-foreground">
                {(chunk.bm25_score * 100).toFixed(0)}%
              </strong>
            </span>
            <span>
              Hybrid:{" "}
              <strong className="text-primary">
                {(chunk.score * 100).toFixed(0)}%
              </strong>
            </span>
          </div>

          {/* Keywords matched */}
          {chunk.keywords_matched.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {chunk.keywords_matched.map((kw) => (
                <span
                  key={kw}
                  className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary"
                >
                  {kw}
                </span>
              ))}
            </div>
          )}

          {/* Chunk content */}
          <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
            {chunk.content}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Collapsible sources + pipeline section ────────────────────────────────────

function SourcesSection({ response }: { response: ChatResponse }) {
  const [open, setOpen] = useState(false);
  const chunkCount = response.retrieved_chunks.length;
  const stepCount = response.tool_steps.length;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <span>
          {chunkCount} source{chunkCount !== 1 ? "s" : ""} · {stepCount} pipeline steps
        </span>
      </button>

      {open && (
        <div className="mt-3 space-y-4">
          {/* Keywords used for retrieval */}
          {response.keywords.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Search Keywords
              </p>
              <div className="flex flex-wrap gap-1.5">
                {response.keywords.map((kw) => (
                  <span
                    key={kw}
                    className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {chunkCount > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Source Documents
              </p>
              {response.retrieved_chunks.map((c, i) => (
                <ChunkCard key={c.chunk_id} chunk={c} index={i} />
              ))}
            </div>
          )}

          {stepCount > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Pipeline Steps
              </p>
              {response.tool_steps.map((s, i) => (
                <ToolStepRow key={i} step={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Message bubbles ───────────────────────────────────────────────────────────

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
        {content}
      </div>
    </div>
  );
}

function AssistantBubble({
  content,
  response,
}: {
  content: string;
  response?: ChatResponse;
}) {
  return (
    <div className="flex items-start gap-3">
      {/* Avatar */}
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Bot className="h-4 w-4 text-primary" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Markdown-rendered answer */}
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>

        {/* Sources + pipeline (keywords live inside here) */}
        {response && <SourcesSection response={response} />}
      </div>
    </div>
  );
}

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
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="font-semibold leading-tight">
                  {agent?.name ?? "Loading…"}
                </h1>
                {agent?.description && (
                  <p className="text-sm text-muted-foreground">{agent.description}</p>
                )}
              </div>
            </div>

            {/* Messages */}
            {isLoading ? (
              <div className="flex justify-center py-16">
                <Spinner className="h-5 w-5" />
              </div>
            ) : (
              <div className="space-y-8">
                {isEmpty && (
                  <div className="flex flex-col items-center justify-center gap-3 py-20 text-center text-muted-foreground">
                    <Bot className="h-12 w-12 opacity-20" />
                    <div>
                      <p className="font-medium text-foreground">
                        {agent?.name ?? "Agent"} is ready
                      </p>
                      <p className="mt-1 text-sm">
                        Ask anything about the project's documents.
                      </p>
                    </div>
                  </div>
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
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-sm bg-muted px-4 py-2.5 text-sm text-muted-foreground">
                      <Spinner className="h-4 w-4" />
                      Thinking…
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
                "flex-1 rounded-xl border border-border bg-background px-4 py-3 text-sm",
                "placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-2 focus:ring-primary",
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
              className="h-11 w-11 rounded-xl shrink-0"
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
