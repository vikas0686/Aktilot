import { Link, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import { FilesTab } from "@/components/FilesTab";

export function ProjectFilesPage() {
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <div className="space-y-4">
      <Link
        to={`/projects/${projectId}`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="h-4 w-4" />
        Knowledge Base
      </Link>
      <FilesTab projectId={projectId!} />
    </div>
  );
}
