import { beforeEach, describe, expect, it, vi } from "vitest";

// vi.mock factories are hoisted before const declarations, so we use
// vi.hoisted() to create spy functions that are available in both the factory
// and the test body.
const { mockGet, mockPost, mockPut, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("axios", () => ({
  default: {
    create: () => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
      delete: mockDelete,
    }),
  },
}));

// Import AFTER the mock is registered (vi.mock is hoisted, but explicit order
// makes the intent clear).
import {
  agentChatApi,
  agentsApi,
  chatSessionsApi,
  projectFilesApi,
  projectsApi,
  shareApi,
  publicChatApi,
} from "@/services/api";

beforeEach(() => vi.clearAllMocks());

// ── projectsApi ───────────────────────────────────────────────────────────────

describe("projectsApi", () => {
  it("list → GET /projects", () => {
    projectsApi.list();
    expect(mockGet).toHaveBeenCalledWith("/projects");
  });

  it("get → GET /projects/:id", () => {
    projectsApi.get("proj-1");
    expect(mockGet).toHaveBeenCalledWith("/projects/proj-1");
  });

  it("create → POST /projects with payload", () => {
    projectsApi.create({ name: "Test", description: "Desc" });
    expect(mockPost).toHaveBeenCalledWith("/projects", {
      name: "Test",
      description: "Desc",
    });
  });

  it("create → POST /projects without description", () => {
    projectsApi.create({ name: "Minimal" });
    expect(mockPost).toHaveBeenCalledWith("/projects", { name: "Minimal" });
  });

  it("delete → DELETE /projects/:id", () => {
    projectsApi.delete("proj-1");
    expect(mockDelete).toHaveBeenCalledWith("/projects/proj-1");
  });
});

// ── projectFilesApi ───────────────────────────────────────────────────────────

describe("projectFilesApi", () => {
  it("list → GET /projects/:id/files", () => {
    projectFilesApi.list("proj-1");
    expect(mockGet).toHaveBeenCalledWith("/projects/proj-1/files");
  });

  it("upload → POST /projects/:id/files/upload with FormData", () => {
    const file = new File(["content"], "doc.pdf", { type: "application/pdf" });
    projectFilesApi.upload("proj-1", file);
    expect(mockPost).toHaveBeenCalledTimes(1);
    const [url, body] = mockPost.mock.calls[0];
    expect(url).toBe("/projects/proj-1/files/upload");
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBe(file);
  });

  it("delete → DELETE /projects/:id/files/:fid", () => {
    projectFilesApi.delete("proj-1", "file-42");
    expect(mockDelete).toHaveBeenCalledWith("/projects/proj-1/files/file-42");
  });
});

// ── agentsApi ─────────────────────────────────────────────────────────────────

describe("agentsApi", () => {
  it("listByProject → GET /projects/:id/agents", () => {
    agentsApi.listByProject("proj-1");
    expect(mockGet).toHaveBeenCalledWith("/projects/proj-1/agents");
  });

  it("get → GET /agents/:id", () => {
    agentsApi.get("agent-1");
    expect(mockGet).toHaveBeenCalledWith("/agents/agent-1");
  });

  it("create → POST /projects/:id/agents with data", () => {
    agentsApi.create("proj-1", { name: "Bot", system_prompt: "Be brief." });
    expect(mockPost).toHaveBeenCalledWith("/projects/proj-1/agents", {
      name: "Bot",
      system_prompt: "Be brief.",
    });
  });

  it("update → PUT /agents/:id with data", () => {
    agentsApi.update("agent-1", { name: "Updated Bot" });
    expect(mockPut).toHaveBeenCalledWith("/agents/agent-1", {
      name: "Updated Bot",
    });
  });

  it("delete → DELETE /agents/:id", () => {
    agentsApi.delete("agent-1");
    expect(mockDelete).toHaveBeenCalledWith("/agents/agent-1");
  });
});

// ── agentChatApi ──────────────────────────────────────────────────────────────

describe("agentChatApi", () => {
  it("send → POST /agents/:id/chat with question and session_id", () => {
    agentChatApi.send("agent-1", "session-1", "What is the total?");
    expect(mockPost).toHaveBeenCalledWith("/agents/agent-1/chat", {
      question: "What is the total?",
      session_id: "session-1",
    });
  });
});

// ── chatSessionsApi ───────────────────────────────────────────────────────────

describe("chatSessionsApi", () => {
  it("listByAgent → GET /agents/:id/sessions", () => {
    chatSessionsApi.listByAgent("agent-1");
    expect(mockGet).toHaveBeenCalledWith("/agents/agent-1/sessions");
  });

  it("create → POST /agents/:id/sessions", () => {
    chatSessionsApi.create("agent-1");
    expect(mockPost).toHaveBeenCalledWith("/agents/agent-1/sessions");
  });

  it("messages → GET /sessions/:id/messages", () => {
    chatSessionsApi.messages("session-1");
    expect(mockGet).toHaveBeenCalledWith("/sessions/session-1/messages");
  });
});

// ── shareApi ──────────────────────────────────────────────────────────────────

describe("shareApi", () => {
  it("generate → POST /agents/:id/share with daily cap", () => {
    shareApi.generate("agent-1", 50);
    expect(mockPost).toHaveBeenCalledWith("/agents/agent-1/share", {
      daily_message_cap: 50,
    });
  });

  it("generate → POST /agents/:id/share with null cap when omitted", () => {
    shareApi.generate("agent-1");
    expect(mockPost).toHaveBeenCalledWith("/agents/agent-1/share", {
      daily_message_cap: null,
    });
  });

  it("revoke → DELETE /agents/:id/share", () => {
    shareApi.revoke("agent-1");
    expect(mockDelete).toHaveBeenCalledWith("/agents/agent-1/share");
  });
});

// ── publicChatApi ─────────────────────────────────────────────────────────────

describe("publicChatApi", () => {
  it("getAgent → GET /public/agents/:slug", () => {
    publicChatApi.getAgent("abc123");
    expect(mockGet).toHaveBeenCalledWith("/public/agents/abc123");
  });

  it("listSessions → GET /public/agents/:slug/sessions", () => {
    publicChatApi.listSessions("abc123");
    expect(mockGet).toHaveBeenCalledWith("/public/agents/abc123/sessions");
  });

  it("createSession → POST /public/agents/:slug/sessions", () => {
    publicChatApi.createSession("abc123");
    expect(mockPost).toHaveBeenCalledWith("/public/agents/abc123/sessions");
  });

  it("sessionMessages → GET /public/agents/:slug/sessions/:id/messages", () => {
    publicChatApi.sessionMessages("abc123", "session-1");
    expect(mockGet).toHaveBeenCalledWith(
      "/public/agents/abc123/sessions/session-1/messages"
    );
  });

  it("send → POST /public/agents/:slug/chat with question and session_id", () => {
    publicChatApi.send("abc123", "session-1", "Hello?");
    expect(mockPost).toHaveBeenCalledWith("/public/agents/abc123/chat", {
      question: "Hello?",
      session_id: "session-1",
    });
  });
});
