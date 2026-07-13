import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Layers,
  Send,
  Sparkles,
  Zap,
} from "lucide-react";
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
import { CHAT_MODEL } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { ChatResponse, RetrievedChunk, ToolStep } from "@/types/api";

type LocalMessage = {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
};

const RETRIEVAL_STEP_NAMES = new Set([
  "Extract Keywords",
  "Vector Search",
  "BM25 + Hybrid Rank",
]);

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-current animate-typing-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  );
}

// ── Pipeline step ─────────────────────────────────────────────────────────────

function ToolStepRow({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-lg border border-border text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 transition-colors hover:bg-muted"
      >
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
        <span className="flex-1 text-left font-medium">{step.name}</span>
        <span className="rounded-full bg-muted px-2 py-0.5 font-medium text-muted-foreground">
          {formatDuration(step.duration_ms)}
        </span>
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
    <div className="overflow-hidden rounded-lg border border-border text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 transition-colors hover:bg-muted"
      >
        <div className="flex flex-1 min-w-0 items-center gap-2">
          <span className="truncate font-medium">
            {index + 1}. {chunk.filename} · #{chunk.chunk_index}
          </span>
          {chunk.kw_hits > 0 && (
            <span className="shrink-0 rounded-full bg-warning/10 px-1.5 py-0.5 font-medium text-warning">
              {chunk.kw_hits} kw
            </span>
          )}
        </div>
        <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 font-semibold text-primary">
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
          <div className="flex gap-4 text-muted-foreground">
            <span>
              Vec: <strong className="text-foreground">{(chunk.vec_score * 100).toFixed(0)}%</strong>
            </span>
            <span>
              BM25: <strong className="text-foreground">{(chunk.bm25_score * 100).toFixed(0)}%</strong>
            </span>
            <span>
              Hybrid: <strong className="text-primary">{(chunk.score * 100).toFixed(0)}%</strong>
            </span>
          </div>

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

          <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
            {chunk.content}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Workflow strip + collapsible pipeline/sources detail ─────────────────────

function WorkflowStrip({ response }: { response: ChatResponse }) {
  const [open, setOpen] = useState(false);
  const chunkCount = response.retrieved_chunks.length;
  const totalMs = response.tool_steps.reduce((sum, s) => sum + s.duration_ms, 0);
  const retrievalMs = response.tool_steps
    .filter((s) => RETRIEVAL_STEP_NAMES.has(s.name))
    .reduce((sum, s) => sum + s.duration_ms, 0);

  return (
    <div className="mt-2.5 rounded-lg border border-border/70 bg-muted/30">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 text-left transition-colors hover:bg-muted/60"
      >
        <span className="flex items-center gap-1.5 text-xs font-medium text-success">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Workflow completed
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Zap className="h-3 w-3" />
          {formatDuration(totalMs)}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {formatDuration(retrievalMs)} retrieval
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <FileText className="h-3 w-3" />
          {chunkCount} chunk{chunkCount !== 1 ? "s" : ""}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Sparkles className="h-3 w-3" />
          {CHAT_MODEL}
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs text-primary">
          {open ? "Hide pipeline" : "View pipeline"}
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-border/70 px-3 pb-3 pt-3">
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

          {response.tool_steps.length > 0 && (
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
      <div className="max-w-[75%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
        {content}
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary/20 to-accent/20 ring-1 ring-primary/10">
      <Bot className="h-4 w-4 text-primary" />
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
      <AssistantAvatar />
      <div className="flex-1 min-w-0">
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
        {response && <WorkflowStrip response={response} />}
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
