// Model names injected at build time via VITE_CHAT_MODEL / VITE_EMBEDDING_MODEL.
// Fallbacks mirror the backend defaults (openai).
export const CHAT_MODEL = import.meta.env.VITE_CHAT_MODEL || "gpt-4o-mini";
export const EMBEDDING_MODEL = import.meta.env.VITE_EMBEDDING_MODEL || "text-embedding-3-small";
