import { useNavigate } from "react-router-dom";
import { Bot, CheckCircle2, Circle, FileText, MessageSquare, X } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Step {
  icon: React.ElementType;
  title: string;
  description: string;
  complete: boolean;
  disabled?: boolean;
  onClick?: () => void;
}

function StepItem({ step }: { step: Step }) {
  const Icon = step.icon;
  const StatusIcon = step.complete ? CheckCircle2 : Circle;

  return (
    <button
      onClick={step.onClick}
      disabled={step.disabled || step.complete}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
        step.complete
          ? "cursor-default"
          : step.disabled
            ? "cursor-not-allowed opacity-50"
            : "hover:bg-muted/60"
      )}
    >
      <StatusIcon
        className={cn(
          "h-4 w-4 shrink-0",
          step.complete ? "text-success" : "text-muted-foreground"
        )}
      />
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-primary/10 to-accent/10">
        <Icon className="h-3.5 w-3.5 text-primary" />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-sm font-medium",
            step.complete && "text-muted-foreground line-through"
          )}
        >
          {step.title}
        </p>
        <p className="text-xs text-muted-foreground">{step.description}</p>
      </div>
    </button>
  );
}

interface GettingStartedCardProps {
  projectId: string;
  hasFiles: boolean;
  hasAgents: boolean;
  firstAgentId?: string;
  onDismiss: () => void;
}

export function GettingStartedCard({
  projectId,
  hasFiles,
  hasAgents,
  firstAgentId,
  onDismiss,
}: GettingStartedCardProps) {
  const navigate = useNavigate();

  const steps: Step[] = [
    {
      icon: FileText,
      title: "Upload documents",
      description: "Add PDFs, docs, or connect GitHub",
      complete: hasFiles,
      onClick: () => navigate(`/projects/${projectId}/files`),
    },
    {
      icon: Bot,
      title: "Create an agent",
      description: "Configure your AI assistant",
      complete: hasAgents,
      onClick: () => navigate(`/projects/${projectId}/agents`),
    },
    {
      icon: MessageSquare,
      title: "Start chatting",
      description: "Ask questions about your documents",
      complete: false, // This step is never "complete" — it's the goal
      disabled: !hasAgents,
      onClick: () => {
        if (firstAgentId) {
          navigate(`/projects/${projectId}/agents/${firstAgentId}/chat`);
        } else {
          navigate(`/projects/${projectId}/agents`);
        }
      },
    },
  ];

  const completedCount = steps.filter((s) => s.complete).length;

  return (
    <Card className="relative overflow-hidden border-primary/20 bg-gradient-to-br from-primary/[0.02] to-accent/[0.02]">
      <div className="p-4">
        {/* Header */}
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold">Getting Started</h3>
            <p className="text-xs text-muted-foreground">
              {completedCount} of {steps.length - 1} steps completed
            </p>
          </div>
          <button
            onClick={onDismiss}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="Dismiss"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Steps */}
        <div className="space-y-0.5">
          {steps.map((step) => (
            <StepItem key={step.title} step={step} />
          ))}
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-muted">
        <div
          className="h-full bg-primary transition-all duration-300"
          style={{ width: `${(completedCount / (steps.length - 1)) * 100}%` }}
        />
      </div>
    </Card>
  );
}
