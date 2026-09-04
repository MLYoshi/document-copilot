// Per-message rendering. User messages are right-aligned primary bubbles;
// assistant answers are full-width "document" blocks with the citations
// panel and the evidence-insufficient warning badge.
import { TriangleAlert } from "lucide-react";

import { CitationList } from "@/components/chat/CitationList";
import { Badge } from "@/components/ui/badge";
import type { ChatMessage, Citation, SourcePassage } from "@/chat/types";
import { cn } from "@/lib/utils";

type MessageBubbleProps = {
  message: ChatMessage;
  // True while this assistant message is still being streamed.
  isStreaming?: boolean;
};

export function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-2" aria-label="正在生成回答">
      {[0, 1, 2].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${-0.3 + delay * 0.15}s` }}
        />
      ))}
    </div>
  );
}

export function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const text = message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground">
          {text}
        </div>
      </div>
    );
  }

  const passages: SourcePassage[] = message.parts.flatMap((part) =>
    part.type === "data-citations" ? part.data : []
  );
  const pointers: Citation[] = message.parts.flatMap((part) =>
    part.type === "data-historyCitations" ? part.data : []
  );
  const evidenceInsufficient = message.parts.some(
    (part) => part.type === "data-evidence" && !part.data.evidence_sufficient
  );

  return (
    <div className="animate-in fade-in slide-in-from-bottom-1 duration-300">
      <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
        {text || (isStreaming ? <TypingDots /> : null)}
      </div>
      {evidenceInsufficient ? (
        <Badge className="mt-2 border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-100">
          <TriangleAlert className="size-3" />
          证据不足，请谨慎参考
        </Badge>
      ) : null}
      <CitationList passages={passages} pointers={pointers} />
    </div>
  );
}
