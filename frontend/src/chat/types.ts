import type { UIMessage } from "ai";

// Chat domain + protocol types, mirroring the backend one-to-one:
// threads/messages schemas (backend/app/chat/schemas.py), the assistant
// output contract (backend/app/assistant/outputs.py), and the SSE frame
// sequence (backend/app/chat/streaming.py).

export type Thread = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type MessageRole = "user" | "assistant";

export type Citation = {
  chunk_id: string;
  ordinal: number;
  quote: string | null;
};

export type Message = {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
  citations: Citation[];
};

export type SourcePassage = {
  chunk_id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  score: number;
  section_path: string;
  title: string;
  ticker: string | null;
  form: string | null;
  filing_date: string | null;
  source_url: string | null;
};

// SSE frames — the exact wire protocol emitted by build_answer_events.
export type StartFrame = { type: "start" };
export type TextStartFrame = { type: "text-start"; id: string };
export type TextDeltaFrame = { type: "text-delta"; id: string; delta: string };
export type TextEndFrame = { type: "text-end"; id: string };
export type DataCitationsFrame = {
  type: "data-citations";
  id: string;
  data: SourcePassage[];
};
export type DataEvidenceFrame = {
  type: "data-evidence";
  id: string;
  data: { evidence_sufficient: boolean };
};
export type FinishFrame = { type: "finish" };

export type AnswerStreamFrame =
  | StartFrame
  | TextStartFrame
  | TextDeltaFrame
  | TextEndFrame
  | DataCitationsFrame
  | DataEvidenceFrame
  | FinishFrame;

// Data parts the backend attaches to the assistant answer, keyed by the
// part name (chunk type is `data-${name}`). These become typed parts on
// ChatMessage and drive the citations/evidence UI. `historyCitations` is
// client-constructed only: persisted citations are quote pointers
// (chunk_id + verbatim quote), while full SourcePassage bodies exist solely
// on the live stream — history never pretends passages were re-fetched.
export type ChatDataParts = {
  citations: SourcePassage[];
  historyCitations: Citation[];
  evidence: { evidence_sufficient: boolean };
};

export type ChatMessageMetadata = {
  createdAt: string;
};

export type ChatMessage = UIMessage<ChatMessageMetadata, ChatDataParts>;
