// History hydration: fetches a thread's persisted messages and maps them to
// UIMessages the AI SDK chat hook can consume, so a reloaded thread renders
// exactly like the live stream left it.
import { api } from "@/lib/api";
import type { ChatMessage, Message } from "@/chat/types";

function toUIMessage(message: Message): ChatMessage {
  const parts: ChatMessage["parts"] = [{ type: "text", text: message.content }];
  if (message.role === "assistant" && message.citations.length > 0) {
    parts.push({ type: "data-historyCitations", data: message.citations });
  }
  return {
    id: message.id,
    role: message.role,
    metadata: { createdAt: message.created_at },
    parts,
  };
}

export async function listMessages(threadId: string): Promise<ChatMessage[]> {
  const messages = await api.get<Message[]>(`/threads/${threadId}/messages`);
  return messages.map(toUIMessage);
}
