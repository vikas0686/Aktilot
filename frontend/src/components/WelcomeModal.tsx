import { Bot, FileText, MessageSquare } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AktilotIcon } from "@/components/AktilotIcon";

const STEPS = [
  {
    icon: FileText,
    title: "Upload documents",
    description: "PDFs, docs, or connect a GitHub repo",
  },
  {
    icon: Bot,
    title: "Create an agent",
    description: "Configure how the AI responds to questions",
  },
  {
    icon: MessageSquare,
    title: "Start chatting",
    description: "Ask questions, get answers with sources",
  },
] as const;

interface WelcomeModalProps {
  open: boolean;
  onClose: () => void;
}

export function WelcomeModal({ open, onClose }: WelcomeModalProps) {
  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent className="max-w-md text-center">
        <div className="flex flex-col items-center gap-6 py-2">
          {/* Logo and headline */}
          <div className="flex flex-col items-center gap-3">
            <AktilotIcon size={48} />
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                Welcome to Aktilot
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Chat with your documents. On your infrastructure.
              </p>
            </div>
          </div>

          {/* Steps */}
          <div className="w-full space-y-3">
            {STEPS.map((step, index) => (
              <div
                key={step.title}
                className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-3 text-left"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-accent/15">
                  <step.icon className="h-4 w-4 text-primary" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    <span className="text-muted-foreground">{index + 1}.</span>{" "}
                    {step.title}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <Button onClick={onClose} className="w-full">
            Get Started
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
