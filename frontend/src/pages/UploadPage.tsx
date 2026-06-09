import { useCallback, useState } from "react";
import { Upload, Loader2, Scissors, Trash2, FileText, FileType, BarChart3 } from "lucide-react";
import { useFiles, useUploadFile, useDeleteFile, useChunkFile, useChunkStats } from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import type { FileRecord } from "@/types/api";

type UploadStatus = { file: File; status: "uploading" | "done" | "error" };

function ChunkBadge({ status, count }: { status: FileRecord["chunk_status"]; count: number }) {
  if (status === "chunked") return <Badge variant="success">{count} chunks</Badge>;
  if (status === "chunking") return <Badge variant="warning">Processing…</Badge>;
  return <Badge variant="secondary">Not chunked</Badge>;
}

export function UploadPage() {
  const [uploading, setUploading] = useState<UploadStatus[]>([]);
  const [dragging, setDragging] = useState(false);

  const { data: files } = useFiles();
  const { data: stats } = useChunkStats();
  const upload = useUploadFile();
  const del = useDeleteFile();
  const chunk = useChunkFile();

  const processFiles = useCallback(
    (files: File[]) => {
      const valid = files.filter((f) =>
        [".pdf", ".txt", ".doc", ".docx"].some((ext) => f.name.toLowerCase().endsWith(ext))
      );
      if (!valid.length) return;

      valid.forEach((file) => {
        setUploading((prev) => [...prev, { file, status: "uploading" }]);
        upload.mutate(file, {
          onSuccess: () =>
            setUploading((prev) => prev.map((u) => u.file === file ? { ...u, status: "done" } : u)),
          onError: () =>
            setUploading((prev) => prev.map((u) => u.file === file ? { ...u, status: "error" } : u)),
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

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">Documents</h1>

      {/* Upload zone */}
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 cursor-pointer transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/50"
        )}
      >
        <Upload className="h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground text-center">
          Drag & drop files here, or <span className="text-primary font-medium">click to browse</span>
        </p>
        <p className="text-xs text-muted-foreground">PDF · TXT · DOC · DOCX</p>
        <input type="file" multiple accept=".pdf,.txt,.doc,.docx" className="sr-only" onChange={onInputChange} />
      </label>

      {/* Upload progress (transient) */}
      {uploading.filter((u) => u.status === "uploading").length > 0 && (
        <ul className="space-y-2">
          {uploading.filter((u) => u.status === "uploading").map((u, i) => (
            <li key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Uploading {u.file.name}…
            </li>
          ))}
        </ul>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Total Chunks", value: stats.total_chunks },
            { label: "Files Chunked", value: stats.total_files_chunked },
            { label: "Index Size", value: stats.index_size },
          ].map(({ label, value }) => (
            <Card key={label}>
              <CardContent className="flex items-center gap-3 py-3">
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-xl font-bold">{value}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* File list */}
      {files && files.length > 0 && (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">File</th>
                <th className="text-left px-4 py-3 font-medium">Size</th>
                <th className="text-left px-4 py-3 font-medium">Chunks</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => {
                const isChunking = chunk.isPending && chunk.variables === f.id;
                const isDeleting = del.isPending && del.variables === f.id;
                const ext = f.filename.split(".").pop()?.toLowerCase();
                return (
                  <tr key={f.id} className="border-t border-border hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {ext === "pdf" ? (
                          <FileType className="h-4 w-4 text-red-400 shrink-0" />
                        ) : ext === "doc" || ext === "docx" ? (
                          <FileType className="h-4 w-4 text-blue-600 shrink-0" />
                        ) : (
                          <FileText className="h-4 w-4 text-blue-400 shrink-0" />
                        )}
                        <span className="truncate max-w-[200px]">{f.filename}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {f.size < 1048576 ? `${(f.size / 1024).toFixed(1)} KB` : `${(f.size / 1048576).toFixed(1)} MB`}
                    </td>
                    <td className="px-4 py-3">
                      <ChunkBadge status={isChunking ? "chunking" : f.chunk_status} count={f.chunk_count} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => chunk.mutate(f.id)}
                          disabled={isChunking}
                        >
                          {isChunking ? (
                            <><Spinner className="h-3 w-3 mr-1" />Chunking…</>
                          ) : (
                            <><Scissors className="h-3 w-3 mr-1" />{f.chunk_status === "chunked" ? "Re-chunk" : "Chunk"}</>
                          )}
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => del.mutate(f.id)}
                          disabled={isDeleting}
                          aria-label={`Delete ${f.filename}`}
                        >
                          {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-destructive" />}
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {files?.length === 0 && uploading.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
          <FileText className="h-10 w-10 opacity-30" />
          <p className="text-sm">No files yet. Upload one above.</p>
        </div>
      )}
    </div>
  );
}
