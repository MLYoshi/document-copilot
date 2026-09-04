// Custom AI SDK transport for the FastAPI chat endpoints. Handles Bearer
// injection, rewriting the UIMessage[] payload into the backend's single
// `question` field, and one 401 → refresh → retry round (same semantics as
// src/lib/api.ts). Uses raw fetch instead of http.request, which buffers
// JSON and imposes a 15s timeout — the RAG pipeline can stream longer, and
// abortSignal is the only cancellation a stream needs.
import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { getAccessToken, refreshAccessToken } from "@/auth/auth";
import { env } from "@/lib/env";
import { ApiError } from "@/lib/http";
import type { ChatMessage } from "@/chat/types";

function extractQuestion(messages: UIMessage[]): string {
  const lastUser = [...messages].reverse().find((message) => message.role === "user");
  if (!lastUser) {
    throw new ApiError("No user message to send", { status: 400 });
  }
  return lastUser.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n");
}

function extractDetail(payload: unknown): string | undefined {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return undefined;
}

async function toApiError(response: Response): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => undefined);
  const detail = extractDetail(payload);
  return new ApiError(detail ?? `Request failed with status ${response.status}`, {
    status: response.status,
    detail,
  });
}

async function requestStream(
  chatId: string,
  question: string,
  abortSignal: AbortSignal | undefined,
): Promise<Response> {
  const send = (token: string | null): Promise<Response> =>
    fetch(`${env.apiBaseUrl}/threads/${chatId}/messages/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question }),
      signal: abortSignal,
    }).catch((error: unknown) => {
      if (abortSignal?.aborted) throw error;
      throw new ApiError("Network request failed", { isNetworkError: true });
    });

  const response = await send(getAccessToken());
  if (response.status !== 401) return response;

  // Access token expired or invalid: single-flight refresh, retry once.
  let newToken: string;
  try {
    newToken = await refreshAccessToken();
  } catch {
    window.location.replace("/login");
    throw new ApiError("Session expired. Please sign in again.", { status: 401 });
  }
  return send(newToken);
}

// Split the SSE byte stream into UIMessageChunks. The backend only emits
// `data: {...}\n\n` frames (see build_answer_events); the buffer stitches
// frames split across network chunks.
function toChunkStream(body: ReadableStream<Uint8Array>): ReadableStream<UIMessageChunk> {
  let buffer = "";
  return body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(
      new TransformStream<string, UIMessageChunk>({
        transform(chunk, controller) {
          buffer += chunk;
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            for (const line of frame.split("\n")) {
              if (!line.startsWith("data:")) continue;
              const payload = line.slice("data:".length).trim();
              if (!payload) continue;
              try {
                controller.enqueue(JSON.parse(payload) as UIMessageChunk);
              } catch {
                throw new ApiError("Malformed stream frame from server", {
                  isNetworkError: true,
                });
              }
            }
            boundary = buffer.indexOf("\n\n");
          }
        },
      }),
    );
}

export class BackendChatTransport implements ChatTransport<ChatMessage> {
  async sendMessages({
    chatId,
    messages,
    abortSignal,
  }: Parameters<ChatTransport<ChatMessage>["sendMessages"]>[0]): Promise<ReadableStream<UIMessageChunk>> {
    const question = extractQuestion(messages);
    const response = await requestStream(chatId, question, abortSignal);
    if (!response.ok) {
      throw await toApiError(response);
    }
    if (!response.body) {
      throw new ApiError("Empty stream response", { isNetworkError: true });
    }
    return toChunkStream(response.body);
  }

  // The backend has no reconnect/resume endpoint.
  reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return Promise.resolve(null);
  }
}
