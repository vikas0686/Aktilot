import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquare,
  Plus,
} from "lucide-react";
import {
  useCreateProject,
  useProjects,
  useProjectAgents,
} from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { Project } from "@/types/api";

// ── New Project modal ─────────────────────────────────────────────────────────

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useCreateProject();
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), description: description.trim() || undefined },
      {
        onSuccess: (project) => {
          onClose();
          navigate(`/projects/${project.id}`);
        },
      }
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Project</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Name *</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="My Project"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Description</label>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
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

// ── Agents sub-tree (only mounts when the project row is expanded) ─────────────

function AgentsSubTree({ projectId }: { projectId: string }) {
  const { data: agents, isLoading } = useProjectAgents(projectId);
  const [open, setOpen] = useState(true);
  const location = useLocation();
  const agentsPath = `/projects/${projectId}/agents`;
  const isAgentsActive = location.pathname === agentsPath;

  return (
    <div>
      {/* Row: chevron (toggle) + "Agents" label (navigates to /agents page) */}
      <div className="flex items-center gap-0.5">
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label={open ? "Collapse agents" : "Expand agents"}
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
        <Link
          to={agentsPath}
          className={cn(
            "flex flex-1 min-w-0 items-center gap-1.5 rounded px-2 py-1.5 text-sm font-medium transition-colors",
            isAgentsActive
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <Bot className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1">Agents</span>
          {isLoading && <Loader2 className="h-3 w-3 animate-spin opacity-50" />}
        </Link>
      </div>

      {/* Individual agents */}
      {open && (
        <div className="ml-6 space-y-0.5 border-l border-border pl-2">
          {agents?.map((agent) => {
            const chatPath = `/projects/${projectId}/agents/${agent.id}/chat`;
            const isActive = location.pathname === chatPath;
            return (
              <Link
                key={agent.id}
                to={chatPath}
                className={cn(
                  "flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{agent.name}</span>
              </Link>
            );
          })}

          {/* New Agent shortcut */}
          <Link
            to={agentsPath}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5 shrink-0" />
            <span>New Agent</span>
          </Link>
        </div>
      )}
    </div>
  );
}

// ── Single project row ────────────────────────────────────────────────────────

function ProjectTreeItem({ project }: { project: Project }) {
  const location = useLocation();
  const projectPath = `/projects/${project.id}`;
  const isOnProject = location.pathname.startsWith(projectPath);
  const [open, setOpen] = useState(false);

  // Auto-expand when the active route is inside this project
  useEffect(() => {
    if (isOnProject) setOpen(true);
  }, [isOnProject]);

  // "Knowledge Base" is active only on the exact project path (not /agents or /agents/*)
  const isKbActive = location.pathname === projectPath;

  return (
    <div>
      {/* Project row */}
      <div className="flex items-center gap-0.5">
        <button
          onClick={() => setOpen((o) => !o)}
          className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label={open ? "Collapse" : "Expand"}
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>
        <Link
          to={projectPath}
          className={cn(
            "flex flex-1 min-w-0 items-center gap-2 rounded px-2 py-1.5 text-sm font-medium transition-colors",
            isOnProject
              ? "text-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <FolderOpen
            className={cn(
              "h-4 w-4 shrink-0",
              isOnProject ? "text-primary" : ""
            )}
          />
          <span className="truncate">{project.name}</span>
        </Link>
      </div>

      {/* Children */}
      {open && (
        <div className="ml-6 space-y-0.5 border-l border-border pl-2">
          {/* Knowledge Base */}
          <Link
            to={projectPath}
            className={cn(
              "flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors",
              isKbActive
                ? "bg-primary/10 font-medium text-primary"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <FileText className="h-3.5 w-3.5 shrink-0" />
            <span>Knowledge Base</span>
          </Link>

          {/* Agents sub-tree — fetches agents lazily on mount */}
          <AgentsSubTree projectId={project.id} />
        </div>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { data: projects, isLoading } = useProjects();
  const [showCreate, setShowCreate] = useState(false);

  return (
    <>
      <aside className="flex w-60 shrink-0 flex-col overflow-hidden border-r border-border bg-card">
        {/* Workspace header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Workspace
          </span>
          <button
            onClick={() => setShowCreate(true)}
            title="New Project"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Tree */}
        <div className="flex-1 overflow-y-auto p-2">
          {/* Projects label */}
          <div className="mb-1 px-2 py-1">
            <Link
              to="/"
              className="text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
            >
              Projects
            </Link>
          </div>

          {isLoading ? (
            <div className="flex justify-center py-6">
              <Spinner className="h-4 w-4" />
            </div>
          ) : projects?.length === 0 ? (
            <div className="px-2 py-4 text-center">
              <p className="text-xs text-muted-foreground">No projects yet.</p>
              <button
                onClick={() => setShowCreate(true)}
                className="mt-1.5 text-xs text-primary hover:underline"
              >
                Create your first project
              </button>
            </div>
          ) : (
            <div className="space-y-0.5">
              {projects?.map((p) => (
                <ProjectTreeItem key={p.id} project={p} />
              ))}
            </div>
          )}
        </div>
      </aside>

      {showCreate && (
        <NewProjectModal onClose={() => setShowCreate(false)} />
      )}
    </>
  );
}
