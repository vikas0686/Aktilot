import { Scissors, BarChart3 } from "lucide-react";
import { useFiles, useChunkFile, useChunkStats } from "@/hooks/useApi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import type { FileRecord } from "@/types/api";

function StatusBadge({ status }: { status: FileRecord["chunk_status"] }) {
  if (status === "chunked") return <Badge variant="success">Chunked</Badge>;
  if (status === "chunking") return <Badge variant="warning">Processing…</Badge>;
  return <Badge variant="secondary">Not chunked</Badge>;
}

export function ChunkPage() {
  const { data: files, isLoading } = useFiles();
  const { data: stats } = useChunkStats();
  const chunk = useChunkFile();

  if (isLoading) return <div className="p-6 flex justify-center"><Spinner className="h-6 w-6" /></div>;

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-6">Chunk Documents</h1>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: "Total Chunks", value: stats.total_chunks },
            { label: "Files Chunked", value: stats.total_files_chunked },
            { label: "Index Size", value: stats.index_size },
          ].map(({ label, value }) => (
            <Card key={label}>
              <CardContent className="flex items-center gap-3 py-4">
                <BarChart3 className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="text-2xl font-bold">{value}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {!files?.length ? (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
          <Scissors className="h-12 w-12 opacity-30" />
          <p>Upload files first to enable chunking.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="text-left px-4 py-3 font-medium">File</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Chunks</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {files.map((f) => {
                const isChunking = chunk.isPending && chunk.variables === f.id;
                return (
                  <tr key={f.id} className="border-t border-border hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 truncate max-w-[250px]">{f.filename}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={isChunking ? "chunking" : f.chunk_status} />
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {f.chunk_count > 0 ? f.chunk_count : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
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
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
