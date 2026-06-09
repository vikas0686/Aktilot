import { Trash2, FileText, FileType, Loader2 } from "lucide-react";
import { useFiles, useDeleteFile } from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { FileRecord } from "@/types/api";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function chunkBadge(status: FileRecord["chunk_status"], count: number) {
  if (status === "chunked") return <Badge variant="success">{count} chunks</Badge>;
  if (status === "chunking") return <Badge variant="warning">Chunking…</Badge>;
  return <Badge variant="secondary">Not chunked</Badge>;
}

export function FilesPage() {
  const { data: files, isLoading } = useFiles();
  const del = useDeleteFile();

  if (isLoading) return <div className="p-6 flex justify-center"><Spinner className="h-6 w-6" /></div>;

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-6">Context Files</h1>

      {!files?.length ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
          <FileText className="h-12 w-12 opacity-30" />
          <p>No files uploaded yet.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">File</th>
                <th className="text-left px-4 py-3 font-medium">Size</th>
                <th className="text-left px-4 py-3 font-medium">Uploaded</th>
                <th className="text-left px-4 py-3 font-medium">Chunks</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id} className="border-t border-border hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 flex items-center gap-2">
                    {f.filename.endsWith(".pdf") ? (
                      <FileType className="h-4 w-4 text-red-400 shrink-0" />
                    ) : f.filename.match(/\.docx?$/i) ? (
                      <FileType className="h-4 w-4 text-blue-600 shrink-0" />
                    ) : (
                      <FileText className="h-4 w-4 text-blue-400 shrink-0" />
                    )}
                    <span className="truncate max-w-[200px]">{f.filename}</span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{formatBytes(f.size)}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(f.uploaded_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">{chunkBadge(f.chunk_status, f.chunk_count)}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => del.mutate(f.id)}
                      disabled={del.isPending && del.variables === f.id}
                      aria-label={`Delete ${f.filename}`}
                    >
                      {del.isPending && del.variables === f.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4 text-destructive" />
                      )}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
