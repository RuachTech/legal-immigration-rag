/**
 * Type definitions for the Legal Immigration RAG System frontend
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  rationales?: Rationale[];
  timestamp: Date;
}

export interface Citation {
  source: string;        // "Immigration Rules, Appendix Skilled Worker"
  section: string;       // "SW 8.1"
  url: string;          // GOV.UK link
  excerpt: string;      // Relevant text snippet
}

export interface Rationale {
  chunkId: string;
  explanation: string;  // Why this chunk is relevant
  confidence: number;   // 0-1 score
}

export interface Session {
  sessionId: string;
  messages: ChatMessage[];
  createdAt: Date;
}
