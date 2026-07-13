import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  FileText,
  FolderOpen,
  Loader2,
  MessageSquare,
  Plus,
} from "lucide-react";
import {
  useCreateProject,
  useProjects,
  useProject,
  useProjectAgents,
} from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const navItemClass = (active: boolean) =>
  cn(
    "relative flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
    active
      ? cn(
          "bg-primary/10 font-medium text-primary",
          "before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full before:bg-primary"
        )
      : "text-muted-foreground hover:bg-muted hover:text-foreground"
  );

// Sidebar isn't inside the routed <Route> tree (it's a sibling in AppShell), so
// it can't use useParams() — parse the project/agent context from the URL directly.
const PROJECT_ROUTE_RE =
  /^\/projects\/([^/]+)(?:\/agents(?:\/([^/]+)\/chat(?:\/([^/]+))?)?)?$/;

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
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="My Project"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Description</label>
            <input
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
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

// ── Workspace-level nav: flat list of all projects ────────────────────────────

function AllProjectsNav({ onCreate }: { onCreate: () => void }) {
  const { data: projects, isLoading } = useProjects();

  if (isLoading) {
    return (
      <div className="space-y-1.5 p-2">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-9 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (projects?.length === 0) {
    return (
      <div className="p-2">
        <EmptyState
          size="sm"
          icon={FolderOpen}
          title="No projects yet"
          action={
            <button
              onClick={onCreate}
              className="text-xs font-medium text-primary hover:underline"
            >
              Create your first project
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-0.5 p-2">
      {projects?.map((p) => (
        <Link key={p.id} to={`/projects/${p.id}`} className={navItemClass(false)}>
          <FolderOpen className="h-4 w-4 shrink-0" />
          <span className="truncate">{p.name}</span>
        </Link>
      ))}
    </div>
  );
}

// ── Project-scoped nav: shown once you're inside a project ───────────────────

function ProjectContextNav({
  projectId,
  agentId,
}: {
  projectId: string;
  agentId?: string;
}) {
  const location = useLocation();
  const { data: project, isLoading: projectLoading } = useProject(projectId);
  const { data: agents, isLoading: agentsLoading } = useProjectAgents(projectId);

  const kbPath = `/projects/${projectId}`;
  const agentsPath = `/projects/${projectId}/agents`;
  const isKbActive = location.pathname === kbPath;
  const isAgentsActive = location.pathname === agentsPath;

  return (
    <div className="flex-1 overflow-y-auto p-2">
      <Link
        to="/"
        className="mb-3 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        All Projects
      </Link>

      <div className="mb-4 px-2.5">
        {projectLoading ? (
          <Skeleton className="h-5 w-32" />
        ) : (
          <>
            <p className="truncate text-sm font-semibold">{project?.name}</p>
            {project?.description && (
              <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                {project.description}
              </p>
            )}
          </>
        )}
      </div>

      <div className="space-y-0.5">
        <Link to={kbPath} className={navItemClass(isKbActive)}>
          <FileText className="h-3.5 w-3.5 shrink-0" />
          <span>Knowledge Base</span>
        </Link>

        <Link to={agentsPath} className={cn(navItemClass(isAgentsActive), "font-medium")}>
          <Bot className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1">Agents</span>
          {agentsLoading && <Loader2 className="h-3 w-3 animate-spin opacity-50" />}
        </Link>

        {!agentsLoading && agents && agents.length > 0 && (
          <div className="ml-6 space-y-0.5 border-l border-border pl-2">
            {agents.map((agent) => {
              const chatPath = `/projects/${projectId}/agents/${agent.id}/chat`;
              const isActive = agent.id === agentId;
              return (
                <Link key={agent.id} to={chatPath} className={navItemClass(isActive)}>
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{agent.name}</span>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export function Sidebar() {
  const location = useLocation();
  const [showCreate, setShowCreate] = useState(false);

  const match = location.pathname.match(PROJECT_ROUTE_RE);
  const projectId = match?.[1];
  const agentId = match?.[2];

  return (
    <>
      <aside className="flex w-64 shrink-0 flex-col overflow-hidden border-r border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {projectId ? "Project" : "Projects"}
          </span>
          <button
            onClick={() => setShowCreate(true)}
            title="New Project"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        </div>

        {projectId ? (
          <ProjectContextNav projectId={projectId} agentId={agentId} />
        ) : (
          <div className="flex-1 overflow-y-auto">
            <AllProjectsNav onCreate={() => setShowCreate(true)} />
          </div>
        )}
      </aside>

      {showCreate && <NewProjectModal onClose={() => setShowCreate(false)} />}
    </>
  );
}
