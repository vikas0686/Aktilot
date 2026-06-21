import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Loader2, MessageSquare, Pencil, Plus, Trash2 } from "lucide-react";
import {
  useProjectAgents,
  useCreateAgent,
  useUpdateAgent,
  useDeleteAgent,
} from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types/api";

// ── Create / Edit modal ───────────────────────────────────────────────────────

function AgentFormModal({
  projectId,
  agent,
  onClose,
}: {
  projectId: string;
  agent?: Agent;
  onClose: () => void;
}) {
  const [name, setName] = useState(agent?.name ?? "");
  const [description, setDescription] = useState(agent?.description ?? "");
  const [systemPrompt, setSystemPrompt] = useState(agent?.system_prompt ?? "");
  const [topK, setTopK] = useState(agent?.top_k ?? 2);

  const create = useCreateAgent(projectId);
  const update = useUpdateAgent(projectId);
  const isEdit = !!agent;
  const isPending = isEdit ? update.isPending : create.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const data = {
      name: name.trim(),
      description: description.trim() || undefined,
      system_prompt: systemPrompt.trim(),
      top_k: Math.max(1, Math.min(10, topK)),
    };
    if (isEdit) {
      update.mutate({ agentId: agent.id, data }, { onSuccess: onClose });
    } else {
      create.mutate(data, { onSuccess: onClose });
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Agent" : "New Agent"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Name *</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Support Bot"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Description</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="What does this agent do?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">System Prompt</label>
            <p className="text-xs text-muted-foreground">
              Instructions sent to the LLM on every chat request for this agent.
            </p>
            <textarea
              className="w-full resize-none rounded-md border border-border bg-background px-3 py-2 font-mono text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="You are a helpful assistant. Answer questions based only on the provided context. If the answer is not in the context, say so clearly."
              rows={6}
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Chunks sent to LLM</label>
            <p className="text-xs text-muted-foreground">
              How many top-ranked document chunks to include in each answer. Default: 2, max: 10.
            </p>
            <input
              type="number"
              min={1}
              max={10}
              className="w-24 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              value={topK}
              onChange={(e) => setTopK(Math.max(1, Math.min(10, Number(e.target.value))))}
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || isPending}>
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isEdit ? (
                "Save"
              ) : (
                "Create"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Agent card ────────────────────────────────────────────────────────────────

function AgentCard({
  agent,
  projectId,
}: {
  agent: Agent;
  projectId: string;
}) {
  const navigate = useNavigate();
  const del = useDeleteAgent(projectId);
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const isDeleting = del.isPending && del.variables === agent.id;

  const handleDelete = () => {
    if (confirming) {
      del.mutate(agent.id, { onSettled: () => setConfirming(false) });
    } else {
      setConfirming(true);
    }
  };

  return (
    <>
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/40">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <Bot className="h-4 w-4 shrink-0 text-primary" />
            <span className="truncate text-sm font-medium">{agent.name}</span>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button
              onClick={() => setEditing(true)}
              title="Edit agent"
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleDelete}
              onMouseLeave={() => setConfirming(false)}
              disabled={isDeleting}
              title={confirming ? "Click again to confirm" : "Delete agent"}
              className={cn(
                "rounded px-1.5 py-1 text-xs font-medium transition-colors",
                confirming
                  ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
                  : "text-muted-foreground hover:text-destructive"
              )}
            >
              {isDeleting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : confirming ? (
                "Delete?"
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </div>

        {/* Description */}
        {agent.description && (
          <p className="line-clamp-2 text-sm text-muted-foreground">
            {agent.description}
          </p>
        )}

        {/* System prompt preview */}
        {agent.system_prompt && (
          <div className="rounded-md bg-muted/50 px-3 py-2">
            <p className="line-clamp-2 font-mono text-xs text-muted-foreground">
              {agent.system_prompt}
            </p>
          </div>
        )}

        {/* top_k badge */}
        <p className="text-xs text-muted-foreground">
          Sends top <strong className="text-foreground">{agent.top_k}</strong> chunk{agent.top_k !== 1 ? "s" : ""} to LLM
        </p>

        <Button
          size="sm"
          className="mt-auto w-full"
          onClick={() =>
            navigate(`/projects/${projectId}/agents/${agent.id}/chat`)
          }
        >
          <MessageSquare className="h-4 w-4" />
          Open Chat
        </Button>
      </div>

      {editing && (
        <AgentFormModal
          projectId={projectId}
          agent={agent}
          onClose={() => setEditing(false)}
        />
      )}
    </>
  );
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export function AgentsTab({ projectId }: { projectId: string }) {
  const { data: agents, isLoading } = useProjectAgents(projectId);
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {agents
            ? `${agents.length} agent${agents.length !== 1 ? "s" : ""}`
            : ""}
        </p>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" />
          New Agent
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-5 w-5" />
        </div>
      ) : agents?.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground">
          <Bot className="h-10 w-10 opacity-30" />
          <p className="text-sm">No agents yet.</p>
          <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" />
            Create your first agent
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {agents?.map((a) => (
            <AgentCard key={a.id} agent={a} projectId={projectId} />
          ))}
        </div>
      )}

      {showCreate && (
        <AgentFormModal
          projectId={projectId}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}
