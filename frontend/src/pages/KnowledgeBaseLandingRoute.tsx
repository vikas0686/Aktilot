import { useParams } from "react-router-dom";
import { KnowledgeBaseLanding } from "@/components/KnowledgeBaseLanding";

export function KnowledgeBaseLandingRoute() {
  const { projectId } = useParams<{ projectId: string }>();
  return <KnowledgeBaseLanding projectId={projectId!} />;
}
