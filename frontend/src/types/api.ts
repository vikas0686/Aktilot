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
}

export interface ChatResponse {
  answer: string;
  tool_steps: ToolStep[];
  retrieved_chunks: RetrievedChunk[];
}

export interface ChunkStats {
  total_chunks: number;
  total_files_chunked: number;
  index_size: number;
}
