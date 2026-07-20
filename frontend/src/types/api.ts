export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ProjectFile {
  id: string;
  project_id: string;
  filename: string;
  size: number;
  chunk_status: "pending" | "chunking" | "chunked" | "error";
  chunk_count: number;
  uploaded_at: string;
}

export interface Agent {
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

export interface ShareLink {
  share_slug: string;
  share_path: string;
  daily_message_cap: number | null;
}

export interface PublicAgent {
  name: string;
  description: string | null;
}

export interface AgentChatMessage {
  id: string;
  agent_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  agent_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface FileRecord {
  id: string;
  filename: string;
  size: number;
  uploaded_at: string;
  chunk_status: "not_chunked" | "chunking" | "chunked";
  chunk_count: number;
}

export interface ToolStep {
  name: string;
  start_time: string;
  end_time: string;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  score: number;
  vec_score: number;
  bm25_score: number;
  kw_hits: number;
  keywords_matched: string[];
}

export interface ChatResponse {
  answer: string;
  tool_steps: ToolStep[];
  retrieved_chunks: RetrievedChunk[];
  keywords: string[];
}

// Visitor-facing share-link chat response — deliberately excludes
// tool_steps/retrieved_chunks, which the backend never sends for this route.
export interface PublicChatResponse {
  answer: string;
}

export interface ChunkStats {
  total_chunks: number;
  total_files_chunked: number;
  index_size: number;
}

export interface GithubInstallUrl {
  install_url: string;
}

export interface GithubInstallation {
  id: string;
  project_id: string;
  account_login: string;
  account_type: string;
  created_at: string;
}

export interface GithubAvailableRepo {
  full_name: string;
  default_branch: string;
  private: boolean;
}

export interface GithubConnection {
  id: string;
  project_id: string;
  repo_full_name: string;
  default_branch: string;
  sync_status: "pending" | "syncing" | "synced" | "error";
  file_count: number;
  chunk_count: number;
  last_synced_at: string | null;
  error_message: string | null;
  created_at: string;
}
