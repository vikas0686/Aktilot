import { useNavigate } from "react-router-dom";
import { ArrowRight, Github, UploadCloud } from "lucide-react";
import { useProjectFiles, useGithubConnections } from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

function SourceCard({
  icon: Icon,
  title,
  description,
  stat,
  cta,
  onClick,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  stat?: string;
  cta: string;
  onClick: () => void;
}) {
  return (
    <Card
      onClick={onClick}
      className={cn(
        "group flex cursor-pointer flex-col justify-between gap-6 p-6 transition-all",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
      )}
    >
      <div>
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-accent/15">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <h3 className="mt-4 text-base font-semibold tracking-tight">{title}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        {stat && <p className="mt-3 text-xs font-medium text-muted-foreground">{stat}</p>}
      </div>

      <Button className="w-full" variant="secondary">
        {cta}
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
      </Button>
    </Card>
  );
}

export function KnowledgeBaseLanding({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const { data: files } = useProjectFiles(projectId);
  const { data: connections } = useGithubConnections(projectId);

  const fileCount = files?.length ?? 0;
  const repoCount = connections?.length ?? 0;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <SourceCard
        icon={UploadCloud}
        title="Uploaded Files"
        description="Upload PDFs and documents to build this project's knowledge base."
        stat={fileCount > 0 ? `${fileCount} file${fileCount === 1 ? "" : "s"} uploaded` : "No files yet"}
        cta="Upload files"
        onClick={() => navigate("files")}
      />
      <SourceCard
        icon={Github}
        title="GitHub Repository"
        description="Connect a GitHub repo to index its code and issues alongside your files."
        stat={repoCount > 0 ? `${repoCount} repo${repoCount === 1 ? "" : "s"} connected` : "Not connected"}
        cta="Connect GitHub"
        onClick={() => navigate("github")}
      />
    </div>
  );
}
