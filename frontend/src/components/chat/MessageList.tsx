// Scrollable message stream with auto-scroll to bottom, a history-loading
// skeleton, and a typing indicator before the first streamed token arrives.
import { useEffect, useRef } from "react";

import { MessageBubble, TypingDots } from "@/components/chat/MessageBubble";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChatMessage } from "@/chat/types";
import type { ChatStatus } from "ai";

type MessageListProps = {
  messages: ChatMessage[];
  status: ChatStatus;
  // True while a thread's history is being fetched (shows skeletons).
  isLoading?: boolean;
};

function SkeletonThread() {
  return (
    <div className="space-y-6" aria-label="加载历史消息">
      {[64, 80, 56].map((width, index) => (
        <div
          key={index}
          className={index % 2 === 0 ? "flex justify-end" : "space-y-2"}
        >
          <div
            className={`h-10 animate-pulse rounded-2xl bg-muted ${index % 2 === 0 ? "" : "w-full"}`}
            style={index % 2 === 0 ? { width: `${width}%` } : undefined}
          />
        </div>
      ))}
    </div>
  );
}

export function MessageList({ messages, status, isLoading = false }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView();
  }, [messages, status, isLoading]);

  const lastMessage = messages[messages.length - 1];

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-4 py-6">
        {isLoading ? (
          <SkeletonThread />
        ) : (
          <>
            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                isStreaming={
                  status === "streaming" && message === lastMessage && message.role === "assistant"
                }
              />
            ))}
            {status === "submitted" ? <TypingDots /> : null}
          </>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
