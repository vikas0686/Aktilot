import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Clock, FileText, FolderOpen, Loader2, Plus, Trash2 } from "lucide-react";
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
  useProjectFiles,
  useProjectAgents,
} from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { Project } from "@/types/api";

// ── Create modal ──────────────────────────────────────────────────────────────

function CreateProjectModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useCreateProject();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), description: description.trim() || undefined },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          onClose();
        },
      }
    );
  };

  const handleClose = () => {
    setName("");
    setDescription("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Project</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Name *</label>
            <input
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="My Project"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Description</label>
            <textarea
              className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="What is this project about?"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={handleClose}>
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

// ── Derived status badge ──────────────────────────────────────────────────────

function ProjectStatusBadge({ isLoading, hasFiles, isProcessing }: {
  isLoading: boolean;
  hasFiles: boolean;
  isProcessing: boolean;
}) {
  if (isLoading) return <Skeleton className="h-5 w-16 rounded-full" />;
  if (isProcessing) return <Badge variant="warning">Processing</Badge>;
  if (hasFiles) return <Badge variant="success">Active</Badge>;
  return <Badge variant="secondary">Empty</Badge>;
}

// ── Project card ──────────────────────────────────────────────────────────────

function ProjectCard({ project }: { project: Project }) {
  const navigate = useNavigate();
  const del = useDeleteProject();
  const [confirming, setConfirming] = useState(false);
  const isDeleting = del.isPending && del.variables === project.id;

  const { data: files, isLoading: filesLoading } = useProjectFiles(project.id);
  const { data: agents, isLoading: agentsLoading } = useProjectAgents(project.id);

  const isProcessing =
    files?.some((f) => f.chunk_status === "pending" || f.chunk_status === "chunking") ?? false;

  const lastActivityIso = [project.created_at, ...(files?.map((f) => f.uploaded_at) ?? [])].sort(
    (a, b) => new Date(b).getTime() - new Date(a).getTime()
  )[0];

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirming) {
      del.mutate(project.id, { onSettled: () => setConfirming(false) });
    } else {
      setConfirming(true);
    }
  };

  return (
    <Card
      className="group flex flex-col rounded-xl transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md cursor-pointer"
      onClick={() => navigate(`/projects/${project.id}`)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-accent/15">
              <FolderOpen className="h-4 w-4 text-primary" />
            </div>
            <CardTitle className="truncate text-base">{project.name}</CardTitle>
          </div>

          <button
            onClick={handleDelete}
            onMouseLeave={() => setConfirming(false)}
            disabled={isDeleting}
            title={confirming ? "Click again to confirm" : "Delete project"}
            className={cn(
              "shrink-0 rounded-md px-1.5 py-1 text-xs font-medium transition-colors",
              confirming
                ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
                : "text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive"
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
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        {project.description ? (
          <p className="line-clamp-2 text-sm text-muted-foreground">{project.description}</p>
        ) : (
          <p className="text-sm italic text-muted-foreground/60">No description</p>
        )}

        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            {filesLoading ? (
              <Skeleton className="h-3.5 w-4" />
            ) : (
              <span className="font-medium text-foreground">{files?.length ?? 0}</span>
            )}
            docs
          </span>
          <span className="flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" />
            {agentsLoading ? (
              <Skeleton className="h-3.5 w-4" />
            ) : (
              <span className="font-medium text-foreground">{agents?.length ?? 0}</span>
            )}
            agents
          </span>
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {lastActivityIso ? formatRelativeTime(lastActivityIso) : "—"}
          </span>
          <ProjectStatusBadge
            isLoading={filesLoading}
            hasFiles={(files?.length ?? 0) > 0}
            isProcessing={isProcessing}
          />
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function ProjectsPage() {
  const { data: projects, isLoading } = useProjects();
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="mx-auto max-w-5xl px-6 py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Each project has its own document context and agents.
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-[188px] rounded-xl" />
          ))}
        </div>
      ) : projects?.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No projects yet"
          description="Create your first project to start uploading documents and building agents."
          action={
            <Button variant="outline" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4" />
              Create your first project
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects?.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}

      <CreateProjectModal open={showCreate} onClose={() => setShowCreate(false)} />
    </div>
  );
}
