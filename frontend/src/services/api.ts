import axios from "axios";
import type { Project, ProjectFile, Agent, AgentChatMessage, FileRecord, ChatResponse, ChunkStats } from "@/types/api";

const api = axios.create({ baseURL: "/api" });

export const projectsApi = {
  list: () => api.get<Project[]>("/projects"),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  create: (data: { name: string; description?: string }) =>
    api.post<Project>("/projects", data),
  delete: (id: string) => api.delete(`/projects/${id}`),
};

export const projectFilesApi = {
  list: (projectId: string) =>
    api.get<ProjectFile[]>(`/projects/${projectId}/files`),
  upload: (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<ProjectFile>(`/projects/${projectId}/files/upload`, fd);
  },
  delete: (projectId: string, fileId: string) =>
    api.delete(`/projects/${projectId}/files/${fileId}`),
};

type AgentPayload = { name?: string; description?: string; system_prompt?: string };

export const agentsApi = {
  listByProject: (projectId: string) =>
    api.get<Agent[]>(`/projects/${projectId}/agents`),
  get: (agentId: string) => api.get<Agent>(`/agents/${agentId}`),
  create: (projectId: string, data: AgentPayload) =>
    api.post<Agent>(`/projects/${projectId}/agents`, data),
  update: (agentId: string, data: AgentPayload) =>
    api.put<Agent>(`/agents/${agentId}`, data),
  delete: (agentId: string) => api.delete(`/agents/${agentId}`),
};

export const agentChatApi = {
  send: (agentId: string, question: string) =>
    api.post<ChatResponse>(`/agents/${agentId}/chat`, { question }),
  messages: (agentId: string) =>
    api.get<AgentChatMessage[]>(`/agents/${agentId}/messages`),
};

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
