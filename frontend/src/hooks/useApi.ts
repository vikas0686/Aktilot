import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { filesApi, chunksApi, chatApi } from "@/services/api";

export const FILES_KEY = ["files"] as const;
export const STATS_KEY = ["chunk-stats"] as const;

export function useFiles() {
  return useQuery({
    queryKey: FILES_KEY,
    queryFn: () => filesApi.list().then((r) => r.data),
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => filesApi.upload(file).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: FILES_KEY }),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => filesApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FILES_KEY });
      qc.invalidateQueries({ queryKey: STATS_KEY });
    },
  });
}

export function useChunkFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => chunksApi.chunk(id).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FILES_KEY });
      qc.invalidateQueries({ queryKey: STATS_KEY });
    },
  });
}

export function useChunkStats() {
  return useQuery({
    queryKey: STATS_KEY,
    queryFn: () => chunksApi.stats().then((r) => r.data),
  });
}

export function useSendMessage() {
  return useMutation({
    mutationFn: (question: string) => chatApi.send(question).then((r) => r.data),
  });
}
