import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Mock the entire API service layer ─────────────────────────────────────────
vi.mock("@/services/api", () => ({
  projectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
  },
  projectFilesApi: {
    list: vi.fn(),
    upload: vi.fn(),
    delete: vi.fn(),
  },
  agentsApi: {
    listByProject: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
  agentChatApi: {
    send: vi.fn(),
  },
  chatSessionsApi: {
    listByAgent: vi.fn(),
    create: vi.fn(),
    messages: vi.fn(),
  },
  filesApi: { list: vi.fn(), upload: vi.fn(), delete: vi.fn() },
  chunksApi: { chunk: vi.fn(), stats: vi.fn() },
  chatApi: { send: vi.fn() },
  shareApi: {
    generate: vi.fn(),
    revoke: vi.fn(),
  },
  publicChatApi: {
    getAgent: vi.fn(),
    listSessions: vi.fn(),
    createSession: vi.fn(),
    sessionMessages: vi.fn(),
    send: vi.fn(),
  },
}));

import { agentChatApi, agentsApi, chatSessionsApi, projectFilesApi, projectsApi, shareApi, publicChatApi } from "@/services/api";
import {
  useAgent,
  useAgentSessions,
  useCreateAgent,
  useCreateChatSession,
  useCreateProject,
  useCreatePublicSession,
  useDeleteAgent,
  useDeleteProject,
  useDeleteProjectFile,
  useGenerateShareLink,
  useProject,
  useProjectAgents,
  useProjectFiles,
  useProjects,
  usePublicAgent,
  usePublicSessionMessages,
  usePublicSessions,
  useRevokeShareLink,
  useSessionMessages,
  useSendAgentMessage,
  useSendPublicMessage,
  useUpdateAgent,
  useUploadProjectFile,
} from "@/hooks/useApi";

// ── Wrapper helpers ───────────────────────────────────────────────────────────

/** Fresh QueryClient per test — no state bleeds between tests. */
function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

/** Shared QueryClient — needed to test that mutations invalidate query caches. */
function makeSharedWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

const PROJECT = { id: "p1", name: "Alpha", description: null, created_at: "2024-01-01T00:00:00Z" };
const AGENT = { id: "a1", project_id: "p1", name: "Bot", description: null, system_prompt: "", top_k: 2, created_at: "2024-01-01T00:00:00Z" };
const FILE_CHUNKED = { id: "f1", project_id: "p1", filename: "doc.pdf", size: 1024, chunk_status: "chunked" as const, chunk_count: 5, uploaded_at: "2024-01-01T00:00:00Z" };
const FILE_PENDING = { ...FILE_CHUNKED, id: "f2", chunk_status: "pending" as const, chunk_count: 0 };
const FILE_CHUNKING = { ...FILE_CHUNKED, id: "f3", chunk_status: "chunking" as const, chunk_count: 0 };

// resetAllMocks (not clearAllMocks) clears mockResolvedValueOnce queues, preventing
// cross-test contamination when a test that uses fake timers exits early.
beforeEach(() => vi.resetAllMocks());
afterEach(() => vi.useRealTimers());

// ── useProjects ───────────────────────────────────────────────────────────────

describe("useProjects", () => {
  it("returns data on success", async () => {
    vi.mocked(projectsApi.list).mockResolvedValue({ data: [PROJECT] } as any);
    const { result } = renderHook(() => useProjects(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([PROJECT]);
  });

  it("surfaces fetch errors", async () => {
    vi.mocked(projectsApi.list).mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useProjects(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

// ── useProject ────────────────────────────────────────────────────────────────

describe("useProject", () => {
  it("fetches a project by id", async () => {
    vi.mocked(projectsApi.get).mockResolvedValue({ data: PROJECT } as any);
    const { result } = renderHook(() => useProject("p1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(PROJECT);
    expect(projectsApi.get).toHaveBeenCalledWith("p1");
  });

  it("does not fetch when id is empty", async () => {
    const { result } = renderHook(() => useProject(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(projectsApi.get).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ── useCreateProject ──────────────────────────────────────────────────────────

describe("useCreateProject", () => {
  it("calls create and returns the new project", async () => {
    vi.mocked(projectsApi.create).mockResolvedValue({ data: PROJECT } as any);
    vi.mocked(projectsApi.list).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useCreateProject(), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync({ name: "Alpha" });
    });

    expect(projectsApi.create).toHaveBeenCalledWith({ name: "Alpha" });
    expect(returned).toEqual(PROJECT);
  });

  it("invalidates projects list after create", async () => {
    const { wrapper } = makeSharedWrapper();
    const updated = [PROJECT, { ...PROJECT, id: "p2", name: "Beta" }];

    vi.mocked(projectsApi.list)
      .mockResolvedValueOnce({ data: [PROJECT] } as any)
      .mockResolvedValueOnce({ data: updated } as any);
    vi.mocked(projectsApi.create).mockResolvedValue({ data: updated[1] } as any);

    const { result: listResult } = renderHook(() => useProjects(), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(1);

    const { result: createResult } = renderHook(() => useCreateProject(), { wrapper });
    await act(async () => {
      await createResult.current.mutateAsync({ name: "Beta" });
    });

    await waitFor(() => expect(listResult.current.data).toHaveLength(2));
  });
});

// ── useDeleteProject ──────────────────────────────────────────────────────────

describe("useDeleteProject", () => {
  it("calls delete with the project id", async () => {
    vi.mocked(projectsApi.delete).mockResolvedValue({ data: null } as any);
    vi.mocked(projectsApi.list).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useDeleteProject(), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync("p1");
    });
    expect(projectsApi.delete).toHaveBeenCalledWith("p1");
  });

  it("invalidates projects list after delete", async () => {
    const { wrapper } = makeSharedWrapper();

    vi.mocked(projectsApi.list)
      .mockResolvedValueOnce({ data: [PROJECT] } as any)
      .mockResolvedValueOnce({ data: [] } as any);
    vi.mocked(projectsApi.delete).mockResolvedValue({ data: null } as any);

    const { result: listResult } = renderHook(() => useProjects(), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(1);

    const { result: delResult } = renderHook(() => useDeleteProject(), { wrapper });
    await act(async () => {
      await delResult.current.mutateAsync("p1");
    });

    await waitFor(() => expect(listResult.current.data).toHaveLength(0));
  });
});

// ── useProjectFiles ───────────────────────────────────────────────────────────

describe("useProjectFiles", () => {
  it("fetches files for a project", async () => {
    vi.mocked(projectFilesApi.list).mockResolvedValue({ data: [FILE_CHUNKED] } as any);
    const { result } = renderHook(() => useProjectFiles("p1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([FILE_CHUNKED]);
    expect(projectFilesApi.list).toHaveBeenCalledWith("p1");
  });

  it("does not fetch when projectId is empty", async () => {
    const { result } = renderHook(() => useProjectFiles(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(projectFilesApi.list).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("polls every 3 s while a file is pending", async () => {
    // vi.advanceTimersByTimeAsync is used instead of waitFor because waitFor's
    // internal retry setTimeout deadlocks when fake timers are active.
    vi.useFakeTimers();
    vi.mocked(projectFilesApi.list)
      .mockResolvedValueOnce({ data: [FILE_PENDING] } as any)   // initial fetch
      .mockResolvedValueOnce({ data: [FILE_CHUNKED] } as any);  // poll after 3 s

    const { result } = renderHook(() => useProjectFiles("p1"), { wrapper: makeWrapper() });

    // Small advance flushes initial fetch (microtasks run inside advanceTimersByTimeAsync)
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data![0].chunk_status).toBe("pending");

    // Advance past 3 s to fire the refetch timer and resolve the second fetch
    await act(async () => { await vi.advanceTimersByTimeAsync(3001); });
    expect(result.current.data![0].chunk_status).toBe("chunked");
    expect(projectFilesApi.list).toHaveBeenCalledTimes(2);
  }, 10000);

  it("polls while a file is chunking", async () => {
    vi.useFakeTimers();
    vi.mocked(projectFilesApi.list)
      .mockResolvedValueOnce({ data: [FILE_CHUNKING] } as any)
      .mockResolvedValueOnce({ data: [FILE_CHUNKED] } as any);

    const { result } = renderHook(() => useProjectFiles("p1"), { wrapper: makeWrapper() });

    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(result.current.data![0].chunk_status).toBe("chunking");

    await act(async () => { await vi.advanceTimersByTimeAsync(3001); });
    expect(result.current.data![0].chunk_status).toBe("chunked");
    expect(projectFilesApi.list).toHaveBeenCalledTimes(2);
  }, 10000);

  it("stops polling once all files are settled", async () => {
    vi.useFakeTimers();
    vi.mocked(projectFilesApi.list).mockResolvedValue({ data: [FILE_CHUNKED] } as any);

    renderHook(() => useProjectFiles("p1"), { wrapper: makeWrapper() });

    await act(async () => { await vi.advanceTimersByTimeAsync(50); }); // flush initial fetch
    await act(async () => { await vi.advanceTimersByTimeAsync(9000); }); // 3× potential intervals

    // All files settled from the start → refetchInterval returns false → only 1 call
    expect(projectFilesApi.list).toHaveBeenCalledTimes(1);
  }, 15000);
});

// ── useUploadProjectFile ──────────────────────────────────────────────────────

describe("useUploadProjectFile", () => {
  it("calls upload with the correct projectId and file", async () => {
    vi.mocked(projectFilesApi.upload).mockResolvedValue({ data: FILE_CHUNKED } as any);
    vi.mocked(projectFilesApi.list).mockResolvedValue({ data: [] } as any);

    const file = new File(["content"], "doc.pdf", { type: "application/pdf" });
    const { result } = renderHook(() => useUploadProjectFile("p1"), { wrapper: makeWrapper() });

    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync(file);
    });

    expect(projectFilesApi.upload).toHaveBeenCalledWith("p1", file);
    expect(returned).toEqual(FILE_CHUNKED);
  });

  it("invalidates project files cache after upload", async () => {
    const { wrapper } = makeSharedWrapper();
    const newFile = { ...FILE_CHUNKED, id: "f-new" };

    vi.mocked(projectFilesApi.list)
      .mockResolvedValueOnce({ data: [] } as any)
      .mockResolvedValueOnce({ data: [newFile] } as any);
    vi.mocked(projectFilesApi.upload).mockResolvedValue({ data: newFile } as any);

    const { result: listResult } = renderHook(() => useProjectFiles("p1"), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(0);

    const { result: upResult } = renderHook(() => useUploadProjectFile("p1"), { wrapper });
    const file = new File([""], "doc.pdf");
    await act(async () => { await upResult.current.mutateAsync(file); });

    await waitFor(() => expect(listResult.current.data).toHaveLength(1));
  });
});

// ── useDeleteProjectFile ──────────────────────────────────────────────────────

describe("useDeleteProjectFile", () => {
  it("calls delete with the correct projectId and fileId", async () => {
    vi.mocked(projectFilesApi.delete).mockResolvedValue({ data: null } as any);
    vi.mocked(projectFilesApi.list).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useDeleteProjectFile("p1"), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync("f1");
    });

    expect(projectFilesApi.delete).toHaveBeenCalledWith("p1", "f1");
  });

  it("invalidates project files cache after delete", async () => {
    const { wrapper } = makeSharedWrapper();

    vi.mocked(projectFilesApi.list)
      .mockResolvedValueOnce({ data: [FILE_CHUNKED] } as any)
      .mockResolvedValueOnce({ data: [] } as any);
    vi.mocked(projectFilesApi.delete).mockResolvedValue({ data: null } as any);

    const { result: listResult } = renderHook(() => useProjectFiles("p1"), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(1);

    const { result: delResult } = renderHook(() => useDeleteProjectFile("p1"), { wrapper });
    await act(async () => { await delResult.current.mutateAsync("f1"); });

    await waitFor(() => expect(listResult.current.data).toHaveLength(0));
  });
});

// ── useProjectAgents ──────────────────────────────────────────────────────────

describe("useProjectAgents", () => {
  it("fetches agents for a project", async () => {
    vi.mocked(agentsApi.listByProject).mockResolvedValue({ data: [AGENT] } as any);
    const { result } = renderHook(() => useProjectAgents("p1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([AGENT]);
    expect(agentsApi.listByProject).toHaveBeenCalledWith("p1");
  });

  it("does not fetch when projectId is empty", async () => {
    const { result } = renderHook(() => useProjectAgents(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(agentsApi.listByProject).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ── useAgent ──────────────────────────────────────────────────────────────────

describe("useAgent", () => {
  it("fetches a single agent", async () => {
    vi.mocked(agentsApi.get).mockResolvedValue({ data: AGENT } as any);
    const { result } = renderHook(() => useAgent("a1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(AGENT);
  });

  it("does not fetch when agentId is empty", async () => {
    renderHook(() => useAgent(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(agentsApi.get).not.toHaveBeenCalled();
  });
});

// ── useCreateAgent ────────────────────────────────────────────────────────────

describe("useCreateAgent", () => {
  it("calls create with projectId and payload", async () => {
    vi.mocked(agentsApi.create).mockResolvedValue({ data: AGENT } as any);
    vi.mocked(agentsApi.listByProject).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useCreateAgent("p1"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync({ name: "Bot" });
    });

    expect(agentsApi.create).toHaveBeenCalledWith("p1", { name: "Bot" });
    expect(returned).toEqual(AGENT);
  });

  it("invalidates agents list after create", async () => {
    const { wrapper } = makeSharedWrapper();
    const updatedAgents = [AGENT, { ...AGENT, id: "a2", name: "Second" }];

    vi.mocked(agentsApi.listByProject)
      .mockResolvedValueOnce({ data: [AGENT] } as any)
      .mockResolvedValueOnce({ data: updatedAgents } as any);
    vi.mocked(agentsApi.create).mockResolvedValue({ data: updatedAgents[1] } as any);

    const { result: listResult } = renderHook(() => useProjectAgents("p1"), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(1);

    const { result: mutResult } = renderHook(() => useCreateAgent("p1"), { wrapper });
    await act(async () => { await mutResult.current.mutateAsync({ name: "Second" }); });

    await waitFor(() => expect(listResult.current.data).toHaveLength(2));
  });
});

// ── useUpdateAgent ────────────────────────────────────────────────────────────

describe("useUpdateAgent", () => {
  it("calls update with agentId and data", async () => {
    const updated = { ...AGENT, name: "Renamed", top_k: 5 };
    vi.mocked(agentsApi.update).mockResolvedValue({ data: updated } as any);
    vi.mocked(agentsApi.listByProject).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useUpdateAgent("p1"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync({ agentId: "a1", data: { name: "Renamed", top_k: 5 } });
    });

    expect(agentsApi.update).toHaveBeenCalledWith("a1", { name: "Renamed", top_k: 5 });
    expect(returned).toEqual(updated);
  });

  it("invalidates agents list after update", async () => {
    const { wrapper } = makeSharedWrapper();
    const updatedAgent = { ...AGENT, name: "Renamed" };

    vi.mocked(agentsApi.listByProject)
      .mockResolvedValueOnce({ data: [AGENT] } as any)
      .mockResolvedValueOnce({ data: [updatedAgent] } as any);
    vi.mocked(agentsApi.update).mockResolvedValue({ data: updatedAgent } as any);

    const { result: listResult } = renderHook(() => useProjectAgents("p1"), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data![0].name).toBe("Bot");

    const { result: updateResult } = renderHook(() => useUpdateAgent("p1"), { wrapper });
    await act(async () => {
      await updateResult.current.mutateAsync({ agentId: "a1", data: { name: "Renamed" } });
    });

    await waitFor(() => expect(listResult.current.data![0].name).toBe("Renamed"));
  });
});

// ── useDeleteAgent ────────────────────────────────────────────────────────────

describe("useDeleteAgent", () => {
  it("calls delete with the agentId", async () => {
    vi.mocked(agentsApi.delete).mockResolvedValue({ data: null } as any);
    vi.mocked(agentsApi.listByProject).mockResolvedValue({ data: [] } as any);

    const { result } = renderHook(() => useDeleteAgent("p1"), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync("a1");
    });
    expect(agentsApi.delete).toHaveBeenCalledWith("a1");
  });

  it("invalidates agents list after delete", async () => {
    const { wrapper } = makeSharedWrapper();

    vi.mocked(agentsApi.listByProject)
      .mockResolvedValueOnce({ data: [AGENT] } as any)
      .mockResolvedValueOnce({ data: [] } as any);
    vi.mocked(agentsApi.delete).mockResolvedValue({ data: null } as any);

    const { result: listResult } = renderHook(() => useProjectAgents("p1"), { wrapper });
    await waitFor(() => expect(listResult.current.isSuccess).toBe(true));
    expect(listResult.current.data).toHaveLength(1);

    const { result: delResult } = renderHook(() => useDeleteAgent("p1"), { wrapper });
    await act(async () => { await delResult.current.mutateAsync("a1"); });

    await waitFor(() => expect(listResult.current.data).toHaveLength(0));
  });
});

// ── useAgentSessions ──────────────────────────────────────────────────────────

describe("useAgentSessions", () => {
  it("fetches chat sessions for an agent", async () => {
    const sessions = [
      { id: "s1", agent_id: "a1", title: "Hello", created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    ];
    vi.mocked(chatSessionsApi.listByAgent).mockResolvedValue({ data: sessions } as any);

    const { result } = renderHook(() => useAgentSessions("a1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(sessions);
    expect(chatSessionsApi.listByAgent).toHaveBeenCalledWith("a1");
  });

  it("does not fetch when agentId is empty", async () => {
    const { result } = renderHook(() => useAgentSessions(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(chatSessionsApi.listByAgent).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ── useCreateChatSession ──────────────────────────────────────────────────────

describe("useCreateChatSession", () => {
  it("creates a session for the agent", async () => {
    const session = { id: "s1", agent_id: "a1", title: null, created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" };
    vi.mocked(chatSessionsApi.create).mockResolvedValue({ data: session } as any);

    const { result } = renderHook(() => useCreateChatSession("a1"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync();
    });

    expect(chatSessionsApi.create).toHaveBeenCalledWith("a1");
    expect(returned).toEqual(session);
  });
});

// ── useSessionMessages ────────────────────────────────────────────────────────

describe("useSessionMessages", () => {
  it("fetches messages for a session", async () => {
    const messages = [
      { id: "m1", agent_id: "a1", role: "user", content: "Hello", created_at: "2024-01-01T00:00:00Z" },
      { id: "m2", agent_id: "a1", role: "assistant", content: "Hi!", created_at: "2024-01-01T00:00:01Z" },
    ];
    vi.mocked(chatSessionsApi.messages).mockResolvedValue({ data: messages } as any);

    const { result } = renderHook(() => useSessionMessages("s1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(messages);
    expect(chatSessionsApi.messages).toHaveBeenCalledWith("s1");
  });

  it("does not fetch when sessionId is undefined", async () => {
    const { result } = renderHook(() => useSessionMessages(undefined), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(chatSessionsApi.messages).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

// ── useSendAgentMessage ───────────────────────────────────────────────────────

describe("useSendAgentMessage", () => {
  it("calls send with agentId, sessionId and question", async () => {
    const response = { answer: "42", tool_steps: [], retrieved_chunks: [], keywords: [] };
    vi.mocked(agentChatApi.send).mockResolvedValue({ data: response } as any);

    const { result } = renderHook(() => useSendAgentMessage("a1", "s1"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync("What is the total?");
    });

    expect(agentChatApi.send).toHaveBeenCalledWith("a1", "s1", "What is the total?");
    expect(returned).toEqual(response);
  });

  it("surfaces errors from send", async () => {
    vi.mocked(agentChatApi.send).mockRejectedValue(new Error("Server error"));

    const { result } = renderHook(() => useSendAgentMessage("a1", "s1"), { wrapper: makeWrapper() });

    // Use mutate (fire-and-forget) + waitFor so React Query's async state update
    // is fully settled before we assert.
    act(() => { result.current.mutate("?"); });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it("invalidates the session's cached messages after sending — otherwise switching away and back re-seeds stale (pre-send) history", async () => {
    const { wrapper } = makeSharedWrapper();
    const before = [{ id: "m1", agent_id: "a1", role: "user", content: "old", created_at: "2024-01-01T00:00:00Z" }];
    const after = [
      ...before,
      { id: "m2", agent_id: "a1", role: "user", content: "What is the total?", created_at: "2024-01-01T00:00:01Z" },
    ];
    vi.mocked(chatSessionsApi.messages)
      .mockResolvedValueOnce({ data: before } as any)
      .mockResolvedValueOnce({ data: after } as any);
    const response = { answer: "42", tool_steps: [], retrieved_chunks: [], keywords: [] };
    vi.mocked(agentChatApi.send).mockResolvedValue({ data: response } as any);

    const { result: messagesResult } = renderHook(() => useSessionMessages("s1"), { wrapper });
    await waitFor(() => expect(messagesResult.current.data).toEqual(before));

    const { result: sendResult } = renderHook(() => useSendAgentMessage("a1", "s1"), { wrapper });
    await act(async () => {
      await sendResult.current.mutateAsync("What is the total?");
    });

    await waitFor(() => expect(messagesResult.current.data).toEqual(after));
  });
});

// ── useGenerateShareLink / useRevokeShareLink ─────────────────────────────────

describe("useGenerateShareLink", () => {
  it("generates a share link with the given daily cap", async () => {
    const link = { share_slug: "abc123", share_path: "/share/abc123", daily_message_cap: 50 };
    vi.mocked(shareApi.generate).mockResolvedValue({ data: link } as any);

    const { result } = renderHook(() => useGenerateShareLink("p1"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync({ agentId: "a1", dailyMessageCap: 50 });
    });

    expect(shareApi.generate).toHaveBeenCalledWith("a1", 50);
    expect(returned).toEqual(link);
  });
});

describe("useRevokeShareLink", () => {
  it("revokes the share link for an agent", async () => {
    vi.mocked(shareApi.revoke).mockResolvedValue({} as any);

    const { result } = renderHook(() => useRevokeShareLink("p1"), { wrapper: makeWrapper() });
    await act(async () => {
      await result.current.mutateAsync("a1");
    });

    expect(shareApi.revoke).toHaveBeenCalledWith("a1");
  });
});

// ── Public (shared-link) chat hooks ────────────────────────────────────────────

describe("usePublicAgent", () => {
  it("fetches the public agent view by slug", async () => {
    const agent = { name: "Support Bot", description: "Helps customers" };
    vi.mocked(publicChatApi.getAgent).mockResolvedValue({ data: agent } as any);

    const { result } = renderHook(() => usePublicAgent("abc123"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(agent);
    expect(publicChatApi.getAgent).toHaveBeenCalledWith("abc123");
  });

  it("does not fetch when slug is empty", async () => {
    const { result } = renderHook(() => usePublicAgent(""), { wrapper: makeWrapper() });
    await new Promise((r) => setTimeout(r, 50));
    expect(publicChatApi.getAgent).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("usePublicSessions", () => {
  it("fetches the visitor's own sessions for the shared agent", async () => {
    const sessions = [
      { id: "s1", agent_id: "a1", title: null, created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" },
    ];
    vi.mocked(publicChatApi.listSessions).mockResolvedValue({ data: sessions } as any);

    const { result } = renderHook(() => usePublicSessions("abc123"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(sessions);
    expect(publicChatApi.listSessions).toHaveBeenCalledWith("abc123");
  });
});

describe("useCreatePublicSession", () => {
  it("creates a new visitor session for the shared agent", async () => {
    const session = { id: "s1", agent_id: "a1", title: null, created_at: "2024-01-01T00:00:00Z", updated_at: "2024-01-01T00:00:00Z" };
    vi.mocked(publicChatApi.createSession).mockResolvedValue({ data: session } as any);

    const { result } = renderHook(() => useCreatePublicSession("abc123"), { wrapper: makeWrapper() });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync();
    });

    expect(publicChatApi.createSession).toHaveBeenCalledWith("abc123");
    expect(returned).toEqual(session);
  });
});

describe("usePublicSessionMessages", () => {
  it("fetches messages for the visitor's session", async () => {
    const messages = [
      { id: "m1", agent_id: "a1", role: "user", content: "Hi", created_at: "2024-01-01T00:00:00Z" },
    ];
    vi.mocked(publicChatApi.sessionMessages).mockResolvedValue({ data: messages } as any);

    const { result } = renderHook(() => usePublicSessionMessages("abc123", "s1"), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(messages);
    expect(publicChatApi.sessionMessages).toHaveBeenCalledWith("abc123", "s1");
  });

  it("does not fetch when sessionId is undefined", async () => {
    const { result } = renderHook(() => usePublicSessionMessages("abc123", undefined), {
      wrapper: makeWrapper(),
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(publicChatApi.sessionMessages).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useSendPublicMessage", () => {
  it("calls send with slug, sessionId and question", async () => {
    const response = { answer: "42", tool_steps: [], retrieved_chunks: [], keywords: [] };
    vi.mocked(publicChatApi.send).mockResolvedValue({ data: response } as any);

    const { result } = renderHook(() => useSendPublicMessage("abc123"), {
      wrapper: makeWrapper(),
    });
    let returned: any;
    await act(async () => {
      returned = await result.current.mutateAsync({
        sessionId: "s1",
        question: "What is the total?",
      });
    });

    expect(publicChatApi.send).toHaveBeenCalledWith("abc123", "s1", "What is the total?");
    expect(returned).toEqual(response);
  });

  it("surfaces rate-limit errors from send", async () => {
    vi.mocked(publicChatApi.send).mockRejectedValue(new Error("Too Many Requests"));

    const { result } = renderHook(() => useSendPublicMessage("abc123"), {
      wrapper: makeWrapper(),
    });

    act(() => {
      result.current.mutate({ sessionId: "s1", question: "?" });
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
