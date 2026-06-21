import { useCallback, useId, useState } from "react";
import { FileText, FileType, Loader2, Trash2, Upload, XCircle } from "lucide-react";
import {
  useProjectFiles,
  useUploadProjectFile,
  useDeleteProjectFile,
} from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { ProjectFile } from "@/types/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

const ALLOWED_EXTS = [".pdf", ".txt", ".doc", ".docx"];
const isAllowed = (name: string) =>
  ALLOWED_EXTS.some((ext) => name.toLowerCase().endsWith(ext));

function formatSize(bytes: number): string {
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FileIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "pdf")
    return <FileType className="h-4 w-4 shrink-0 text-red-400" />;
  if (ext === "doc" || ext === "docx")
    return <FileType className="h-4 w-4 shrink-0 text-blue-600" />;
  return <FileText className="h-4 w-4 shrink-0 text-blue-400" />;
}

function ChunkStatusBadge({
  status,
  count,
}: {
  status: ProjectFile["chunk_status"];
  count: number;
}) {
  if (status === "chunked")
    return <Badge variant="success">{count} chunks</Badge>;
  if (status === "chunking")
    return (
      <Badge variant="warning" className="flex items-center gap-1">
        <Loader2 className="h-3 w-3 animate-spin" />
        Processing…
      </Badge>
    );
  if (status === "error")
    return <Badge variant="destructive">Error</Badge>;
  return <Badge variant="secondary">Pending…</Badge>;
}

function FileRow({
  file,
  projectId,
}: {
  file: ProjectFile;
  projectId: string;
}) {
  const del = useDeleteProjectFile(projectId);
  const [confirming, setConfirming] = useState(false);
  const isDeleting = del.isPending && del.variables === file.id;

  const handleDelete = () => {
    if (confirming) {
      del.mutate(file.id, { onSettled: () => setConfirming(false) });
    } else {
      setConfirming(true);
    }
  };

  return (
    <tr className="border-t border-border transition-colors hover:bg-muted/30">
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <FileIcon filename={file.filename} />
          <span className="max-w-[220px] truncate text-sm">{file.filename}</span>
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-muted-foreground whitespace-nowrap">
        {formatSize(file.size)}
      </td>
      <td className="px-4 py-3">
        <ChunkStatusBadge status={file.chunk_status} count={file.chunk_count} />
      </td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={handleDelete}
          onMouseLeave={() => setConfirming(false)}
          disabled={isDeleting}
          title={confirming ? "Click again to confirm" : "Delete file"}
          className={cn(
            "rounded px-2 py-1 text-xs font-medium transition-colors",
            confirming
              ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
              : "text-muted-foreground hover:text-destructive"
          )}
        >
          {isDeleting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : confirming ? (
            "Delete?"
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
        </button>
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type UploadItem = { file: File; status: "uploading" | "done" | "error" };

export function FilesTab({ projectId }: { projectId: string }) {
  const { data: files, isLoading } = useProjectFiles(projectId);
  const upload = useUploadProjectFile(projectId);
  const inputId = useId();

  const [dragging, setDragging] = useState(false);
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  const processFiles = useCallback(
    (selected: File[]) => {
      const valid = selected.filter((f) => isAllowed(f.name));
      if (!valid.length) return;
      valid.forEach((file) => {
        setUploads((prev) => [...prev, { file, status: "uploading" }]);
        upload.mutate(file, {
          onSuccess: () =>
            setUploads((prev) =>
              prev.map((u) =>
                u.file === file ? { ...u, status: "done" } : u
              )
            ),
          onError: () =>
            setUploads((prev) =>
              prev.map((u) =>
                u.file === file ? { ...u, status: "error" } : u
              )
            ),
        });
      });
    },
    [upload]
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    processFiles(Array.from(e.dataTransfer.files));
  };

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) processFiles(Array.from(e.target.files));
    e.target.value = "";
  };

  const inProgress = uploads.filter((u) => u.status === "uploading");
  const failed = uploads.filter((u) => u.status === "error");

  return (
    <div className="space-y-5">
      {/* Drop zone */}
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 transition-colors",
          dragging
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/40"
        )}
      >
        <Upload className="h-7 w-7 text-muted-foreground" />
        <p className="text-center text-sm text-muted-foreground">
          Drag & drop files here, or{" "}
          <span className="font-medium text-primary">click to browse</span>
        </p>
        <p className="text-xs text-muted-foreground">
          PDF · TXT · DOC · DOCX
        </p>
        <input
          id={inputId}
          type="file"
          multiple
          accept=".pdf,.txt,.doc,.docx"
          className="sr-only"
          onChange={onInputChange}
        />
      </label>

      {/* Upload progress */}
      {inProgress.length > 0 && (
        <ul className="space-y-1.5">
          {inProgress.map((u, i) => (
            <li
              key={i}
              className="flex items-center gap-2 text-sm text-muted-foreground"
            >
              <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
              Uploading {u.file.name}…
            </li>
          ))}
        </ul>
      )}

      {/* Upload errors */}
      {failed.length > 0 && (
        <ul className="space-y-1.5">
          {failed.map((u, i) => (
            <li
              key={i}
              className="flex items-center gap-2 text-sm text-destructive"
            >
              <XCircle className="h-4 w-4 shrink-0" />
              Failed to upload {u.file.name}
            </li>
          ))}
        </ul>
      )}

      {/* File list */}
      {isLoading ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-5 w-5" />
        </div>
      ) : files && files.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">File</th>
                <th className="px-4 py-2.5 text-left font-medium">Size</th>
                <th className="px-4 py-2.5 text-left font-medium">Status</th>
                <th className="px-4 py-2.5 text-right font-medium">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <FileRow key={f.id} file={f} projectId={projectId} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        inProgress.length === 0 && (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-muted-foreground">
            <FileText className="h-9 w-9 opacity-30" />
            <p className="text-sm">No files yet. Upload one above.</p>
          </div>
        )
      )}
    </div>
  );
}
