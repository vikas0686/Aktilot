import { useState, useRef, useEffect } from "react";
import { Send, ChevronDown, ChevronRight, CheckCircle, Clock } from "lucide-react";
import { useSendMessage } from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { ChatResponse, ToolStep, RetrievedChunk } from "@/types/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  response?: ChatResponse;
}

function ToolStepRow({ step }: { step: ToolStep }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-md overflow-hidden text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 hover:bg-muted transition-colors"
      >
        <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
        <span className="font-medium flex-1 text-left">{step.name}</span>
        <span className="text-muted-foreground">{step.duration_ms.toFixed(0)}ms</span>
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 space-y-1.5 bg-muted/30 border-t border-border">
          <p className="text-muted-foreground"><span className="font-medium">In:</span> {step.input_summary}</p>
          <p className="text-muted-foreground"><span className="font-medium">Out:</span> {step.output_summary}</p>
          <p className="text-muted-foreground flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {new Date(step.start_time).toLocaleTimeString()} → {new Date(step.end_time).toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}

function ChunkCard({ chunk, index }: { chunk: RetrievedChunk; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-md overflow-hidden text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-2 hover:bg-muted transition-colors"
      >
        <span className="font-medium">Chunk {index + 1} · {chunk.filename}</span>
        <div className="flex items-center gap-2">
          <Badge variant="success">{chunk.score.toFixed(2)}</Badge>
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-1 bg-muted/30 border-t border-border">
          <p className="text-muted-foreground whitespace-pre-wrap leading-relaxed">{chunk.content}</p>
        </div>
      )}
    </div>
  );
}

function SidePanel({ response }: { response: ChatResponse }) {
  return (
    <div className="w-80 shrink-0 border-l border-border overflow-auto p-4 space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Tools Executed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {response.tool_steps.map((s, i) => (
            <ToolStepRow key={i} step={s} />
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Retrieved Chunks</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {response.retrieved_chunks.length === 0 ? (
            <p className="text-xs text-muted-foreground">No chunks retrieved.</p>
          ) : (
            response.retrieved_chunks.map((c, i) => <ChunkCard key={c.chunk_id} chunk={c} index={i} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const [responseKey, setResponseKey] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const send = useSendMessage();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, send.isPending]);

  const handleSend = () => {
    const q = input.trim();
    if (!q || send.isPending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);

    send.mutate(q, {
      onSuccess: (data) => {
        setLastResponse(data);
        setResponseKey((k) => k + 1);
        setMessages((m) => [...m, { role: "assistant", content: data.answer, response: data }]);
      },
      onError: () => {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: "An error occurred. Please try again." },
        ]);
      },
    });
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chat thread */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
              <p className="text-sm">Ask anything about your uploaded documents.</p>
              <p className="text-xs">Make sure files are chunked first.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "flex",
                m.role === "user" ? "justify-end" : "justify-start"
              )}
            >
              <div
                className={cn(
                  "max-w-[75%] rounded-xl px-4 py-3 text-sm whitespace-pre-wrap",
                  m.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                )}
              >
                {m.content}
              </div>
            </div>
          ))}
          {send.isPending && (
            <div className="flex justify-start">
              <div className="bg-muted rounded-xl px-4 py-3 flex items-center gap-2">
                <Spinner className="h-4 w-4" />
                <span className="text-sm text-muted-foreground">Thinking…</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-border p-4">
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Ask a question about your documents…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              disabled={send.isPending}
            />
            <Button onClick={handleSend} disabled={send.isPending || !input.trim()} size="icon">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Side panel — show last response */}
      {lastResponse && <SidePanel key={responseKey} response={lastResponse} />}
    </div>
  );
}
