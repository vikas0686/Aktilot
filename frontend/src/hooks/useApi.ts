import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { projectsApi, projectFilesApi, agentsApi, agentChatApi, chatSessionsApi, filesApi, chunksApi, chatApi, shareApi, publicChatApi } from "@/services/api";
import type { ProjectFile } from "@/types/api";

// ── Projects ──────────────────────────────────────────────────────────────────

export const PROJECTS_KEY = ["projects"] as const;

export function useProjects() {
  return useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: () => projectsApi.list().then((r) => r.data),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: [...PROJECTS_KEY, id],
    queryFn: () => projectsApi.get(id).then((r) => r.data),
    enabled: !!id,
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      projectsApi.create(data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROJECTS_KEY }),
  });
}

// ── Project Files ─────────────────────────────────────────────────────────────

const projectFilesKey = (projectId: string) => ["project-files", projectId] as const;

const isSettling = (f: ProjectFile) =>
  f.chunk_status === "pending" || f.chunk_status === "chunking";

export function useProjectFiles(projectId: string) {
  return useQuery({
    queryKey: projectFilesKey(projectId),
    queryFn: () => projectFilesApi.list(projectId).then((r) => r.data),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const data = query.state.data as ProjectFile[] | undefined;
      return data?.some(isSettling) ? 3000 : false;
    },
  });
}

export function useUploadProjectFile(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      projectFilesApi.upload(projectId, file).then((r) => r.data),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: projectFilesKey(projectId) }),
  });
}

export function useDeleteProjectFile(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileId: string) => projectFilesApi.delete(projectId, fileId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: projectFilesKey(projectId) }),
  });
}

// ── Agents ────────────────────────────────────────────────────────────────────

const agentsKey = (projectId: string) => ["agents", projectId] as const;

type AgentPayload = { name?: string; description?: string; system_prompt?: string; top_k?: number };

export function useProjectAgents(projectId: string) {
  return useQuery({
    queryKey: agentsKey(projectId),
    queryFn: () => agentsApi.listByProject(projectId).then((r) => r.data),
    enabled: !!projectId,
  });
}

export function useCreateAgent(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentPayload) =>
      agentsApi.create(projectId, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentsKey(projectId) }),
  });
}

export function useUpdateAgent(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: AgentPayload }) =>
      agentsApi.update(agentId, data).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentsKey(projectId) }),
  });
}

export function useDeleteAgent(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => agentsApi.delete(agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentsKey(projectId) }),
  });
}

export function useAgent(agentId: string) {
  return useQuery({
    queryKey: ["agent", agentId] as const,
    queryFn: () => agentsApi.get(agentId).then((r) => r.data),
    enabled: !!agentId,
  });
}

// ── Share Links ───────────────────────────────────────────────────────────────

export function useGenerateShareLink(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, dailyMessageCap }: { agentId: string; dailyMessageCap?: number }) =>
      shareApi.generate(agentId, dailyMessageCap).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentsKey(projectId) }),
  });
}

export function useRevokeShareLink(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => shareApi.revoke(agentId),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentsKey(projectId) }),
  });
}

// ── Public (shared-link) chat ──────────────────────────────────────────────────

export function usePublicAgent(slug: string) {
  return useQuery({
    queryKey: ["public-agent", slug] as const,
    queryFn: () => publicChatApi.getAgent(slug).then((r) => r.data),
    enabled: !!slug,
    retry: false,
  });
}

const publicSessionsKey = (slug: string) => ["public-sessions", slug] as const;

export function usePublicSessions(slug: string) {
  return useQuery({
    queryKey: publicSessionsKey(slug),
    queryFn: () => publicChatApi.listSessions(slug).then((r) => r.data),
    enabled: !!slug,
  });
}

export function useCreatePublicSession(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => publicChatApi.createSession(slug).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: publicSessionsKey(slug) }),
  });
}

const publicSessionMessagesKey = (slug: string, sessionId: string) =>
  ["public-session-messages", slug, sessionId] as const;

export function usePublicSessionMessages(slug: string, sessionId: string | undefined) {
  return useQuery({
    queryKey: publicSessionMessagesKey(slug, sessionId ?? ""),
    queryFn: () => publicChatApi.sessionMessages(slug, sessionId!).then((r) => r.data),
    enabled: !!slug && !!sessionId,
  });
}

export function useSendPublicMessage(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sessionId, question }: { sessionId: string; question: string }) =>
      publicChatApi.send(slug, sessionId, question).then((r) => r.data),
    onSuccess: (_data, { sessionId }) => {
      qc.invalidateQueries({ queryKey: publicSessionsKey(slug) });
      qc.invalidateQueries({ queryKey: publicSessionMessagesKey(slug, sessionId) });
    },
  });
}

// ── Chat Sessions ─────────────────────────────────────────────────────────────

const agentSessionsKey = (agentId: string) => ["agent-sessions", agentId] as const;

export function useAgentSessions(agentId: string) {
  return useQuery({
    queryKey: agentSessionsKey(agentId),
    queryFn: () => chatSessionsApi.listByAgent(agentId).then((r) => r.data),
    enabled: !!agentId,
  });
}

export function useCreateChatSession(agentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => chatSessionsApi.create(agentId).then((r) => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: agentSessionsKey(agentId) }),
  });
}

const sessionMessagesKey = (sessionId: string) => ["session-messages", sessionId] as const;

export function useSessionMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: sessionMessagesKey(sessionId ?? ""),
    queryFn: () => chatSessionsApi.messages(sessionId!).then((r) => r.data),
    enabled: !!sessionId,
  });
}

export function useSendAgentMessage(agentId: string, sessionId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (question: string) =>
      agentChatApi.send(agentId, sessionId!, question).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: agentSessionsKey(agentId) });
      if (sessionId) {
        qc.invalidateQueries({ queryKey: sessionMessagesKey(sessionId) });
      }
    },
  });
}

// ── Legacy (old FAISS-based system) ──────────────────────────────────────────

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
