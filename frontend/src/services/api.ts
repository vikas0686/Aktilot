import axios from "axios";
import type { FileRecord, ChatResponse, ChunkStats } from "@/types/api";

const api = axios.create({ baseURL: "/api" });

export const filesApi = {
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<FileRecord>("/files/upload", fd);
  },
  list: () => api.get<FileRecord[]>("/files"),
  delete: (id: string) => api.delete(`/files/${id}`),
};

export const chunksApi = {
  chunk: (id: string) => api.post<{ chunksCreated: number }>(`/chunk/${id}`),
  stats: () => api.get<ChunkStats>("/chunks/stats"),
};

export const chatApi = {
  send: (question: string) => api.post<ChatResponse>("/chat", { question }),
};
