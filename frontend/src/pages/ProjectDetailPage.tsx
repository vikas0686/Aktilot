import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Loader2, Trash2 } from "lucide-react";
import { useProject, useDeleteProject } from "@/hooks/useApi";
import { FilesTab } from "@/components/FilesTab";
import { GitHubTab } from "@/components/GitHubTab";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
      <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full rounded-2xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
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
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-primary">
            Knowledge Base
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
          {project.description && (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {project.description}
            </p>
          )}
        </div>

        {/* Delete project */}
        <button
          onClick={handleDelete}
          onMouseLeave={() => setConfirming(false)}
          disabled={del.isPending}
          title={confirming ? "Click again to confirm delete" : "Delete project"}
          className={cn(
            "mt-1 shrink-0 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
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

      <Tabs defaultValue="files">
        <TabsList>
          <TabsTrigger value="files">Uploaded Files</TabsTrigger>
          <TabsTrigger value="github">GitHub</TabsTrigger>
        </TabsList>
        <TabsContent value="files">
          <FilesTab projectId={project.id} />
        </TabsContent>
        <TabsContent value="github">
          <GitHubTab projectId={project.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
