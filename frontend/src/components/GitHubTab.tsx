import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Github, Loader2, Plug, RefreshCw, Trash2 } from "lucide-react";
import {
  useGithubInstallation,
  useGithubInstallUrl,
  useGithubConnections,
  useAvailableGithubRepos,
  useAvailableGithubInstallations,
  useAttachGithubInstallation,
  useConnectGithubRepo,
  useSyncGithubConnection,
  useDisconnectGithubConnection,
  useDisconnectGithubInstallation,
} from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { GithubConnection } from "@/types/api";

// ── Sync status badge ────────────────────────────────────────────────────────

function SyncStatusBadge({ status }: { status: GithubConnection["sync_status"] }) {
  if (status === "synced") return <Badge variant="success">Synced</Badge>;
  if (status === "error") return <Badge variant="destructive">Error</Badge>;
  return (
    <Badge variant="warning" className="flex items-center gap-1">
      <Loader2 className="h-3 w-3 animate-spin" />
      Syncing…
    </Badge>
  );
}

// ── Add Repository dialog ────────────────────────────────────────────────────

function AddRepoDialog({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const { data: repos, isLoading } = useAvailableGithubRepos(projectId, true);
  const connect = useConnectGithubRepo(projectId);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Github className="h-4 w-4 text-primary" />
            Add Repository
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-11 w-full rounded-lg" />
            ))}
          </div>
        ) : repos && repos.length > 0 ? (
          <ul className="max-h-80 space-y-1.5 overflow-y-auto">
            {repos.map((repo) => {
              const isConnecting =
                connect.isPending && connect.variables?.repoFullName === repo.full_name;
              return (
                <li key={repo.full_name}>
                  <button
                    onClick={() =>
                      connect.mutate(
                        { repoFullName: repo.full_name },
                        { onSuccess: onClose }
                      )
                    }
                    disabled={connect.isPending}
                    className="flex w-full items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors hover:border-primary/40 hover:bg-muted/40 disabled:opacity-50"
                  >
                    <span className="truncate">{repo.full_name}</span>
                    {isConnecting ? (
                      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                    ) : (
                      <Badge variant="secondary">{repo.default_branch}</Badge>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState
            size="sm"
            icon={Github}
            title="No repositories available"
            description="Grant this installation access to a repository from GitHub's settings, then try again."
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

// ── Connection row ────────────────────────────────────────────────────────────

function ConnectionRow({
  connection,
  projectId,
}: {
  connection: GithubConnection;
  projectId: string;
}) {
  const sync = useSyncGithubConnection(projectId);
  const del = useDisconnectGithubConnection(projectId);
  const [confirming, setConfirming] = useState(false);

  const isSyncing =
    connection.sync_status === "pending" || connection.sync_status === "syncing";
  const isDeleting = del.isPending && del.variables === connection.id;

  const handleDelete = () => {
    if (confirming) {
      del.mutate(connection.id, { onSettled: () => setConfirming(false) });
    } else {
      setConfirming(true);
    }
  };

  return (
    <div className="group flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:border-primary/30">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-accent/15">
          <Github className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium">
              {connection.repo_full_name}
            </span>
            <Badge variant="secondary">{connection.default_branch}</Badge>
          </div>
          <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
            <span>{connection.chunk_count} chunks</span>
            <span>
              {connection.last_synced_at
                ? `Synced ${formatRelativeTime(connection.last_synced_at)}`
                : "Never synced"}
            </span>
          </div>
          {connection.sync_status === "error" && connection.error_message && (
            <p
              className="mt-1 truncate text-xs text-destructive"
              title={connection.error_message}
            >
              {connection.error_message}
            </p>
          )}
          {connection.sync_status === "synced" && connection.tree_truncated && (
            <p
              className="mt-1 text-xs text-amber-600 dark:text-amber-500"
              title="GitHub's API truncated this repo's file tree — only part of it was indexed."
            >
              Partially indexed (repo too large)
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <SyncStatusBadge status={connection.sync_status} />
        <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          <button
            onClick={() => sync.mutate(connection.id)}
            disabled={isSyncing || sync.isPending}
            title="Pull the latest data from GitHub"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw
              className={cn(
                "h-3.5 w-3.5",
                (isSyncing || sync.isPending) && "animate-spin"
              )}
            />
          </button>
          <button
            onClick={handleDelete}
            onMouseLeave={() => setConfirming(false)}
            disabled={isDeleting}
            title={confirming ? "Click again to confirm" : "Disconnect repository"}
            className={cn(
              "rounded-md px-1.5 py-1 text-xs font-medium transition-colors",
              confirming
                ? "bg-destructive/10 text-destructive hover:bg-destructive/20 opacity-100"
                : "text-muted-foreground hover:text-destructive"
            )}
          >
            {isDeleting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : confirming ? (
              "Disconnect?"
            ) : (
              <Trash2 className="h-3.5 w-3.5" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main tab ──────────────────────────────────────────────────────────────────

export function GitHubTab({ projectId }: { projectId: string }) {
  const {
    data: installation,
    isLoading: installationLoading,
    isError: notInstalled,
  } = useGithubInstallation(projectId);
  const { data: connections, isLoading: connectionsLoading } =
    useGithubConnections(projectId);
  const installUrl = useGithubInstallUrl(projectId);
  const disconnectInstallation = useDisconnectGithubInstallation(projectId);
  const needsInstallation = !installationLoading && (notInstalled || !installation);
  const { data: availableInstallations } = useAvailableGithubInstallations(
    projectId,
    needsInstallation
  );
  const attachInstallation = useAttachGithubInstallation(projectId);

  const [showAddRepo, setShowAddRepo] = useState(false);
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();

  // Captured once on mount, before the effect below strips the query param —
  // the installation query is still loading at that point, so reading
  // searchParams fresh at render time would find it already gone.
  const [githubStatus] = useState(() => searchParams.get("github"));

  useEffect(() => {
    if (searchParams.has("github")) {
      const next = new URLSearchParams(searchParams);
      next.delete("github");
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnectGithub = () => {
    installUrl.mutate(undefined, {
      onSuccess: (data) => {
        window.location.href = data.install_url;
      },
    });
  };

  const handleDisconnectInstallation = () => {
    if (confirmingDisconnect) {
      disconnectInstallation.mutate(undefined, {
        onSettled: () => setConfirmingDisconnect(false),
      });
    } else {
      setConfirmingDisconnect(true);
    }
  };

  if (installationLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  if (notInstalled || !installation) {
    return (
      <div className="space-y-4">
        {githubStatus === "error" && (
          <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            GitHub connection was not completed. Please try again.
          </p>
        )}
        <EmptyState
          icon={Github}
          title="Connect a GitHub account"
          description="Install the GitHub App to pull repository files and issues into this project's knowledge base."
          action={
            <Button
              size="sm"
              onClick={handleConnectGithub}
              disabled={installUrl.isPending}
            >
              {installUrl.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plug className="h-4 w-4" />
              )}
              Connect GitHub
            </Button>
          }
        />
        {availableInstallations && availableInstallations.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm font-medium">Or reuse an existing connection</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              These GitHub accounts are already connected to other projects.
              GitHub doesn't always redirect back here if the App is already
              installed on an account, so this attaches it directly instead.
            </p>
            <ul className="mt-3 space-y-1.5">
              {availableInstallations.map((inst) => {
                const isAttaching =
                  attachInstallation.isPending &&
                  attachInstallation.variables === inst.installation_id;
                return (
                  <li key={inst.installation_id}>
                    <button
                      onClick={() =>
                        attachInstallation.mutate(inst.installation_id)
                      }
                      disabled={attachInstallation.isPending}
                      className="flex w-full items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-left text-sm transition-colors hover:border-primary/40 hover:bg-muted/40 disabled:opacity-50"
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Github className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        {inst.account_login}
                      </span>
                      {isAttaching ? (
                        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                      ) : (
                        <Badge variant="secondary">Use this</Badge>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2.5 text-sm">
          <Github className="h-4 w-4 text-primary" />
          <span>
            Connected as <span className="font-medium">{installation.account_login}</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setShowAddRepo(true)}>
            <Plug className="h-4 w-4" />
            Add Repository
          </Button>
          <button
            onClick={handleDisconnectInstallation}
            onMouseLeave={() => setConfirmingDisconnect(false)}
            disabled={disconnectInstallation.isPending}
            title={
              confirmingDisconnect ? "Click again to confirm" : "Disconnect GitHub"
            }
            className={cn(
              "rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors",
              confirmingDisconnect
                ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
                : "text-muted-foreground hover:text-destructive"
            )}
          >
            {disconnectInstallation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : confirmingDisconnect ? (
              "Disconnect?"
            ) : (
              "Disconnect"
            )}
          </button>
        </div>
      </div>

      {connectionsLoading ? (
        <div className="space-y-2">
          {[...Array(2)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : connections && connections.length > 0 ? (
        <div className="space-y-2">
          {connections.map((c) => (
            <ConnectionRow key={c.id} connection={c} projectId={projectId} />
          ))}
        </div>
      ) : (
        <EmptyState
          size="sm"
          icon={Github}
          title="No repositories connected"
          description="Add a repository to start pulling its files and issues into this project."
        />
      )}

      {showAddRepo && (
        <AddRepoDialog projectId={projectId} onClose={() => setShowAddRepo(false)} />
      )}
    </div>
  );
}
