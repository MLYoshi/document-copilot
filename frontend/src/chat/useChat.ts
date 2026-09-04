// Thread chat state: the AI SDK chat hook plus history hydration. The view
// is keyed by threadId in ChatPage, so `id` — which the transport uses as
// the backend thread UUID — stays stable for the hook's lifetime.
import { useEffect, useRef, useState } from "react";
import { useChat } from "@ai-sdk/react";

import { listMessages } from "@/chat/history";
import { BackendChatTransport } from "@/chat/transport";
import type { ChatMessage } from "@/chat/types";

const transport = new BackendChatTransport();

type ThreadChatOptions = {
  /** First question of a freshly created thread; sent once after hydration. */
  initialQuestion?: string;
  onInitialQuestionConsumed?: () => void;
  /** Fired when a streamed answer completes; used to refresh the sidebar. */
  onAnswered?: () => void;
};

export function useThreadChat(threadId: string, options: ThreadChatOptions = {}) {
  const { initialQuestion, onInitialQuestionConsumed, onAnswered } = options;

  const [isHydrating, setIsHydrating] = useState(true);
  const [hydrateError, setHydrateError] = useState<string | null>(null);
  const initialSent = useRef(false);

  const chat = useChat<ChatMessage>({
    id: threadId,
    transport,
    onFinish: onAnswered,
  });

  useEffect(() => {
    let cancelled = false;
    // The view is keyed by threadId, so this hook remounts and `isHydrating`
    // starts as true; the async flow below is what flips it back.
    listMessages(threadId)
      .then((messages) => {
        if (!cancelled) chat.setMessages(messages);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHydrateError(error instanceof Error ? error.message : "加载历史消息失败");
        }
      })
      .finally(() => {
        if (!cancelled) setIsHydrating(false);
      });
    return () => {
      cancelled = true;
    };
    // chat.setMessages is a stable bound method of the per-mount Chat
    // instance; depending on the helpers object would re-run every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  useEffect(() => {
    if (!initialQuestion || isHydrating || hydrateError || initialSent.current) return;
    initialSent.current = true;
    onInitialQuestionConsumed?.();
    void chat.sendMessage({ text: initialQuestion });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion, isHydrating, hydrateError]);

  return {
    messages: chat.messages,
    status: chat.status,
    error: chat.error,
    isHydrating,
    hydrateError,
    sendMessage: chat.sendMessage,
    stop: chat.stop,
    clearError: chat.clearError,
  };
}
