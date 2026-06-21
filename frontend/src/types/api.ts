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
}

export interface AgentChatMessage {
  id: string;
  agent_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
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

export interface ChunkStats {
  total_chunks: number;
  total_files_chunked: number;
  index_size: number;
}
