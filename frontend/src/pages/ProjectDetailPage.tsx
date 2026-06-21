import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2, Trash2 } from "lucide-react";
import { useProject, useDeleteProject } from "@/hooks/useApi";
import { FilesTab } from "@/components/FilesTab";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading } = useProject(projectId!);
  const del = useDeleteProject();
  const [confirming, setConfirming] = useState(false);

  const handleDelete = () => {
    if (confirming) {
      del.mutate(projectId!, {
        onSuccess: () => navigate("/"),
      });
    } else {
      setConfirming(true);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center gap-3 py-20 text-muted-foreground">
        <p className="text-sm">Project not found.</p>
        <Link to="/" className="text-sm underline hover:text-foreground">
          Back to projects
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{project.name}</h1>
          {project.description && (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {project.description}
            </p>
          )}
          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Knowledge Base
          </p>
        </div>

        {/* Delete project */}
        <button
          onClick={handleDelete}
          onMouseLeave={() => setConfirming(false)}
          disabled={del.isPending}
          title={confirming ? "Click again to confirm delete" : "Delete project"}
          className={cn(
            "mt-1 shrink-0 rounded px-2.5 py-1.5 text-xs font-medium transition-colors",
            confirming
              ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
              : "text-muted-foreground hover:text-destructive"
          )}
        >
          {del.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : confirming ? (
            "Delete project?"
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </button>
      </div>

      <FilesTab projectId={project.id} />
    </div>
  );
}
