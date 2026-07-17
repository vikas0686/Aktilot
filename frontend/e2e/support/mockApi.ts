/**
 * A small, stateful fake backend used by every e2e test instead of a real
 * FastAPI + Temporal + LLM stack. `page.route("**\/api/**", …)` intercepts
 * every request in the browser network layer before it leaves the page, so
 * nothing here ever depends on a real server being reachable.
 *
 * Rationale for a stateful fake (vs. per-test ad-hoc stubs): the flows under
 * test span multiple screens (create project -> create agent -> chat ->
 * share -> public chat), each reading back state the previous step wrote.
 * A fixed per-request stub can't do that; a tiny in-memory model can.
 */
import type { Page, Route } from "@playwright/test";
import { randomUUID } from "node:crypto";

export interface ChatTurn {
  status?: number;
  answer?: string;
  toolSteps?: Array<{ name: string; output_summary?: string }>;
  retrievedChunks?: Array<Record<string, unknown>>;
  keywords?: string[];
  detail?: string;
}

interface ProjectRecord {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

interface AgentRecord {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  top_k: number;
  created_at: string;
  share_slug: string | null;
  share_daily_message_cap: number | null;
}

interface SessionRecord {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  visitor_owned: boolean;
}

interface MessageRecord {
  id: string;
  agent_id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

const now = () => new Date().toISOString();

export class ApiMock {
  projects: ProjectRecord[] = [];
  agents: AgentRecord[] = [];
  sessions: SessionRecord[] = [];
  messages: MessageRecord[] = [];
  private adminChatScript: ChatTurn[] = [];
  private publicChatScript: ChatTurn[] = [];

  /** Queue scripted admin-chat (`/agents/:id/chat`) responses, consumed in order. */
  scriptAdminChat(...turns: ChatTurn[]) {
    this.adminChatScript.push(...turns);
  }

  /** Queue scripted public-chat (`/public/agents/:slug/chat`) responses. */
  scriptPublicChat(...turns: ChatTurn[]) {
    this.publicChatScript.push(...turns);
  }

  seedProject(overrides: Partial<ProjectRecord> = {}): ProjectRecord {
    const project: ProjectRecord = {
      id: randomUUID(),
      name: "Seed Project",
      description: null,
      created_at: now(),
      ...overrides,
    };
    this.projects.push(project);
    return project;
  }

  seedAgent(projectId: string, overrides: Partial<AgentRecord> = {}): AgentRecord {
    const agent: AgentRecord = {
      id: randomUUID(),
      project_id: projectId,
      name: "Seed Agent",
      description: null,
      system_prompt: "",
      top_k: 2,
      created_at: now(),
      share_slug: null,
      share_daily_message_cap: null,
      ...overrides,
    };
    this.agents.push(agent);
    return agent;
  }

  private defaultChatTurn(question: string): Required<Omit<ChatTurn, "detail">> & {
    detail?: string;
  } {
    return {
      status: 200,
      answer: `Mock answer to: ${question}`,
      toolSteps: [
        { name: "Extract Keywords", output_summary: 'Keywords: ["mock"]' },
        { name: "Vector Search", output_summary: "1 candidates" },
        { name: "BM25 + Hybrid Rank", output_summary: "Top score: 0.920" },
        { name: "Build Context", output_summary: "42 chars" },
        { name: "Generate Answer", output_summary: "18 chars" },
      ],
      retrievedChunks: [
        {
          chunk_id: "c1",
          filename: "handbook.pdf",
          chunk_index: 0,
          content: "Mock retrieved chunk content used to answer the question.",
          score: 0.92,
          vec_score: 0.9,
          bm25_score: 0.94,
          kw_hits: 1,
          keywords_matched: ["mock"],
        },
      ],
      keywords: ["mock"],
    };
  }

  private toolStepsBody(steps: Array<{ name: string; output_summary?: string }>) {
    return steps.map((s) => ({
      name: s.name,
      start_time: now(),
      end_time: now(),
      duration_ms: 12,
      input_summary: "mock input",
      output_summary: s.output_summary ?? "mock output",
    }));
  }

  private json(route: Route, status: number, body: unknown) {
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  }

  private notFound(route: Route) {
    return this.json(route, 404, { detail: "Not found" });
  }

  /** Install the route interceptor on a page. Call once per test. */
  async install(page: Page) {
    await page.route("**/api/**", (route) => this.handle(route));
  }

  private async handle(route: Route) {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname.replace(/^.*\/api/, ""); // strip origin + any base path down to /api
    const segments = path.split("/").filter(Boolean);

    try {
      await this.dispatch(route, method, segments, req);
    } catch (err) {
      // A route the mock doesn't understand is a test-authoring bug, not a
      // silent pass-through — fail loudly instead of letting requests hang.
      await this.json(route, 500, {
        detail: `mockApi: unhandled ${method} ${path}: ${(err as Error).message}`,
      });
    }
  }

  private async dispatch(
    route: Route,
    method: string,
    seg: string[],
    req: ReturnType<Route["request"]>
  ) {
    const body = () => {
      try {
        return req.postDataJSON();
      } catch {
        return {};
      }
    };

    // ── /projects ──────────────────────────────────────────────────────────
    if (seg[0] === "projects" && seg.length === 1 && method === "GET") {
      return this.json(route, 200, this.projects);
    }
    if (seg[0] === "projects" && seg.length === 1 && method === "POST") {
      const b = body();
      const project = this.seedProject({ name: b.name, description: b.description ?? null });
      return this.json(route, 200, project);
    }
    if (seg[0] === "projects" && seg.length === 2 && method === "GET") {
      const project = this.projects.find((p) => p.id === seg[1]);
      return project ? this.json(route, 200, project) : this.notFound(route);
    }
    if (seg[0] === "projects" && seg.length === 2 && method === "DELETE") {
      this.projects = this.projects.filter((p) => p.id !== seg[1]);
      this.agents = this.agents.filter((a) => a.project_id !== seg[1]);
      return this.json(route, 204, null);
    }
    if (seg[0] === "projects" && seg[2] === "files" && method === "GET") {
      return this.json(route, 200, []);
    }
    if (seg[0] === "projects" && seg[2] === "agents" && seg.length === 3 && method === "GET") {
      return this.json(route, 200, this.agents.filter((a) => a.project_id === seg[1]));
    }
    if (seg[0] === "projects" && seg[2] === "agents" && seg.length === 3 && method === "POST") {
      const b = body();
      const agent = this.seedAgent(seg[1], {
        name: b.name,
        description: b.description ?? null,
        system_prompt: b.system_prompt ?? "",
        top_k: b.top_k ?? 2,
      });
      return this.json(route, 200, agent);
    }

    // ── /agents/:id ────────────────────────────────────────────────────────
    if (seg[0] === "agents" && seg.length === 2 && method === "GET") {
      const agent = this.agents.find((a) => a.id === seg[1]);
      return agent ? this.json(route, 200, agent) : this.notFound(route);
    }
    if (seg[0] === "agents" && seg.length === 2 && method === "PUT") {
      const agent = this.agents.find((a) => a.id === seg[1]);
      if (!agent) return this.notFound(route);
      Object.assign(agent, body());
      return this.json(route, 200, agent);
    }
    if (seg[0] === "agents" && seg.length === 2 && method === "DELETE") {
      this.agents = this.agents.filter((a) => a.id !== seg[1]);
      return this.json(route, 204, null);
    }

    // ── /agents/:id/sessions, /sessions/:id/messages ──────────────────────
    if (seg[0] === "agents" && seg[2] === "sessions" && seg.length === 3 && method === "GET") {
      const sessions = this.sessions
        .filter((s) => s.agent_id === seg[1] && !s.visitor_owned)
        .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      return this.json(route, 200, sessions);
    }
    if (seg[0] === "agents" && seg[2] === "sessions" && seg.length === 3 && method === "POST") {
      const session = this.createSession(seg[1], false);
      return this.json(route, 201, session);
    }
    if (seg[0] === "sessions" && seg[2] === "messages" && method === "GET") {
      return this.json(route, 200, this.messagesFor(seg[1]));
    }

    // ── /agents/:id/chat (admin) ──────────────────────────────────────────
    if (seg[0] === "agents" && seg[2] === "chat" && method === "POST") {
      const b = body();
      return this.handleChat(route, {
        agentId: seg[1],
        sessionId: b.session_id,
        question: b.question,
        script: this.adminChatScript,
        public: false,
      });
    }

    // ── /agents/:id/share ──────────────────────────────────────────────────
    if (seg[0] === "agents" && seg[2] === "share" && method === "POST") {
      const agent = this.agents.find((a) => a.id === seg[1]);
      if (!agent) return this.notFound(route);
      const b = body();
      agent.share_slug = `slug-${agent.id.slice(0, 8)}`;
      agent.share_daily_message_cap = b.daily_message_cap ?? null;
      return this.json(route, 200, {
        share_slug: agent.share_slug,
        share_path: `/share/${agent.share_slug}`,
        daily_message_cap: agent.share_daily_message_cap,
      });
    }
    if (seg[0] === "agents" && seg[2] === "share" && method === "DELETE") {
      const agent = this.agents.find((a) => a.id === seg[1]);
      if (!agent) return this.notFound(route);
      agent.share_slug = null;
      agent.share_daily_message_cap = null;
      return this.json(route, 204, null);
    }

    // ── /public/agents/:slug ───────────────────────────────────────────────
    if (seg[0] === "public" && seg[1] === "agents" && seg.length === 3 && method === "GET") {
      const agent = this.agents.find((a) => a.share_slug === seg[2]);
      if (!agent) return this.notFound(route);
      return this.json(route, 200, { name: agent.name, description: agent.description });
    }
    if (seg[0] === "public" && seg[3] === "sessions" && seg.length === 4 && method === "GET") {
      const agent = this.agents.find((a) => a.share_slug === seg[2]);
      if (!agent) return this.notFound(route);
      const sessions = this.sessions
        .filter((s) => s.agent_id === agent.id && s.visitor_owned)
        .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      return this.json(route, 200, sessions);
    }
    if (seg[0] === "public" && seg[3] === "sessions" && seg.length === 4 && method === "POST") {
      const agent = this.agents.find((a) => a.share_slug === seg[2]);
      if (!agent) return this.notFound(route);
      return this.json(route, 201, this.createSession(agent.id, true));
    }
    if (seg[0] === "public" && seg[3] === "sessions" && seg[5] === "messages" && method === "GET") {
      return this.json(route, 200, this.messagesFor(seg[4]));
    }
    if (seg[0] === "public" && seg[3] === "chat" && method === "POST") {
      const agent = this.agents.find((a) => a.share_slug === seg[2]);
      if (!agent) return this.notFound(route);
      const b = body();
      return this.handleChat(route, {
        agentId: agent.id,
        sessionId: b.session_id,
        question: b.question,
        script: this.publicChatScript,
        public: true,
      });
    }

    throw new Error("no matching mock route");
  }

  private createSession(agentId: string, visitorOwned: boolean): SessionRecord {
    const session: SessionRecord = {
      id: randomUUID(),
      agent_id: agentId,
      title: null,
      created_at: now(),
      updated_at: now(),
      visitor_owned: visitorOwned,
    };
    this.sessions.push(session);
    return session;
  }

  private messagesFor(sessionId: string) {
    return this.messages
      .filter((m) => m.session_id === sessionId)
      .map(({ id, agent_id, role, content, created_at }) => ({
        id,
        agent_id,
        role,
        content,
        created_at,
      }));
  }

  private async handleChat(
    route: Route,
    opts: {
      agentId: string;
      sessionId: string;
      question: string;
      script: ChatTurn[];
      public: boolean;
    }
  ) {
    const turn = { ...this.defaultChatTurn(opts.question), ...(opts.script.shift() ?? {}) };

    if (turn.status && turn.status >= 400) {
      return this.json(route, turn.status, { detail: turn.detail ?? "Mock error" });
    }

    const session = this.sessions.find((s) => s.id === opts.sessionId);
    if (session && session.title === null) session.title = opts.question;
    if (session) session.updated_at = now();

    this.messages.push({
      id: randomUUID(),
      agent_id: opts.agentId,
      session_id: opts.sessionId,
      role: "user",
      content: opts.question,
      created_at: now(),
    });
    this.messages.push({
      id: randomUUID(),
      agent_id: opts.agentId,
      session_id: opts.sessionId,
      role: "assistant",
      content: turn.answer!,
      created_at: now(),
    });

    if (opts.public) {
      // Mirrors the real PublicChatResponse: answer only. Any test wanting to
      // simulate a backend that (regressively) leaks pipeline metadata passes
      // toolSteps/retrievedChunks in scriptPublicChat and the extra keys are
      // still included here — the UI must ignore them regardless.
      return this.json(route, 200, {
        answer: turn.answer,
        ...(turn.toolSteps ? { tool_steps: this.toolStepsBody(turn.toolSteps) } : {}),
        ...(turn.retrievedChunks ? { retrieved_chunks: turn.retrievedChunks } : {}),
      });
    }

    return this.json(route, 200, {
      answer: turn.answer,
      tool_steps: this.toolStepsBody(turn.toolSteps ?? []),
      retrieved_chunks: turn.retrievedChunks ?? [],
      keywords: turn.keywords ?? [],
    });
  }
}
