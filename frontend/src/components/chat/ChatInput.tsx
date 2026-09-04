// Composer at the bottom of the chat view. Native form + textarea:
// Enter sends, Shift+Enter inserts a newline, IME composition is
// respected. Input is disabled while an answer streams; the send
// button turns into a stop button.
import { ArrowUp, Square } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ChatStatus } from "ai";

type ChatInputProps = {
  status: ChatStatus;
  onSubmit: (text: string) => void;
  onStop: () => void;
};

export function ChatInput({ status, onSubmit, onStop }: ChatInputProps) {
  const [text, setText] = useState("");
  const streaming = status === "submitted" || status === "streaming";

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed || streaming) return;
    onSubmit(trimmed);
    setText("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    submit();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submit();
  };

  return (
    <div className="border-t bg-background p-4">
      <form
        onSubmit={handleSubmit}
        className="mx-auto flex w-full max-w-[760px] items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-1 focus-within:ring-ring"
      >
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="就申报文件提问，例如：这家公司最新 10-K 的营收同比变化？"
          disabled={streaming}
          rows={1}
          className="max-h-40 min-h-9 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
        />
        {streaming ? (
          <Button
            type="button"
            size="icon"
            variant="outline"
            onClick={onStop}
            aria-label="停止生成"
            className="shrink-0 rounded-full"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!text.trim()}
            aria-label="发送"
            className="shrink-0 rounded-full"
          >
            <ArrowUp className="size-4" />
          </Button>
        )}
      </form>
      <p className="mx-auto mt-2 w-full max-w-[760px] px-1 text-center text-xs text-muted-foreground">
        回答基于申报文件检索生成，请在引用来源中核对原文。
      </p>
    </div>
  );
}
