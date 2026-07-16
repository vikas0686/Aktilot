import { useState } from "react";
import { Check, Copy, Link2, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { useGenerateShareLink, useRevokeShareLink } from "@/hooks/useApi";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { Agent } from "@/types/api";

export function ShareAgentModal({
  projectId,
  agent,
  onClose,
}: {
  projectId: string;
  agent: Agent;
  onClose: () => void;
}) {
  const generate = useGenerateShareLink(projectId);
  const revoke = useRevokeShareLink(projectId);
  const [dailyCap, setDailyCap] = useState<string>(
    agent.share_daily_message_cap ? String(agent.share_daily_message_cap) : ""
  );
  const [copied, setCopied] = useState(false);

  const isShared = !!agent.share_slug;
  const shareUrl = isShared ? `${window.location.origin}/share/${agent.share_slug}` : "";

  const handleGenerate = () => {
    const cap = dailyCap.trim() ? Math.max(1, Number(dailyCap)) : undefined;
    generate.mutate({ agentId: agent.id, dailyMessageCap: cap });
  };

  const handleCopy = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRevoke = () => {
    revoke.mutate(agent.id);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" />
            Share {agent.name}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Anyone with this link can chat with this agent — no login required.
            They'll only see this agent's name and a chat box; nothing about
            this project, its files, or your other agents.
          </p>

          {isShared && (
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Share link</label>
              <div className="flex gap-2">
                <input
                  readOnly
                  className="flex-1 truncate rounded-lg border border-border bg-muted/50 px-3 py-2 font-mono text-xs"
                  value={shareUrl}
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button type="button" variant="outline" size="icon" onClick={handleCopy}>
                  {copied ? (
                    <Check className="h-4 w-4 text-success" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Daily message limit</label>
            <p className="text-xs text-muted-foreground">
              Hard cap on total visitor messages per day, across everyone who
              has this link. Protects you from unbounded API spend if the
              link leaks or goes viral.
              {isShared && " Changing it generates a new link and invalidates the old one."}
            </p>
            <input
              type="number"
              min={1}
              className="w-32 rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="200"
              value={dailyCap}
              onChange={(e) => setDailyCap(e.target.value)}
            />
          </div>

          {isShared && (
            <div className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                Visitor conversations are private — not even you can view them.
                Revoking the link stops new chats but does not delete the agent.
              </span>
            </div>
          )}

          <div className="flex justify-between gap-2 pt-1">
            {isShared ? (
              <Button
                type="button"
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={handleRevoke}
                disabled={revoke.isPending}
              >
                {revoke.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Revoke
              </Button>
            ) : (
              <span />
            )}
            <Button type="button" onClick={handleGenerate} disabled={generate.isPending}>
              {generate.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isShared ? (
                "Regenerate Link"
              ) : (
                "Generate Link"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
