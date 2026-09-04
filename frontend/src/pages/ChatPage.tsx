// Main chat layout: persistent sidebar + either the empty "new chat" state
// or the active thread view. Threads are created lazily on the first
// question (the backend has no title-update endpoint): the new-chat composer
// creates the thread with a title truncated to 200 chars, then navigates to
// /chat/:threadId where the view sends the pending question once history
// hydration completes.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { ThreadSidebar } from "@/components/chat/ThreadSidebar";
import { Button } from "@/components/ui/button";
import { useThreadChat } from "@/chat/useChat";
import { createThread, useThreads } from "@/chat/threads";
import { ApiError } from "@/lib/http";

const SAMPLE_QUESTIONS = [
  "这家公司最新 10-K 中管理层讨论了哪些主要风险因素？",
  "总结最近一季 10-Q 里营收变化及管理层给出的原因。",
  "招股书中对本次募集资金用途是如何描述的？",
];

function errorText(error: Error | undefined): string {
  if (error instanceof ApiError && error.isNetworkError) {
    return "网络请求失败，请检查网络后重试";
  }
  return error?.message ?? "发送失败，请重试";
}

function ChatView({
  threadId,
  title,
  initialQuestion,
  onInitialConsumed,
  onAnswered,
}: {
  threadId: string;
  title: string | undefined;
  initialQuestion?: string;
  onInitialConsumed: () => void;
  onAnswered: () => void;
}) {
  const chat = useThreadChat(threadId, {
    initialQuestion,
    onInitialQuestionConsumed: onInitialConsumed,
    onAnswered,
  });

  const activeError = chat.hydrateError ?? (chat.error ? errorText(chat.error) : null);

  return (
    <>
      <header className="border-b px-4 py-3">
        <h1 className="truncate text-sm font-medium">{title || "新对话"}</h1>
      </header>
      <MessageList messages={chat.messages} status={chat.status} isLoading={chat.isHydrating} />
      {activeError ? (
        <div className="flex items-center justify-between gap-2 border-t border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span>{activeError}</span>
          {chat.error ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-destructive hover:text-destructive"
              onClick={() => chat.clearError()}
            >
              关闭
            </Button>
          ) : null}
        </div>
      ) : null}
      <ChatInput
        status={chat.status}
        onSubmit={(text) => void chat.sendMessage({ text })}
        onStop={() => void chat.stop()}
      />
    </>
  );
}

function EmptyState({
  onCreate,
  creating,
  error,
}: {
  onCreate: (question: string) => void;
  creating: boolean;
  error: string | null;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4">
        <div className="text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            基于 SEC 申报文件的检索式问答，每个回答都附带可核对的原文引用。
          </p>
        </div>
        <div className="flex w-full max-w-md flex-col gap-2">
          {SAMPLE_QUESTIONS.map((question) => (
            <Button
              key={question}
              variant="outline"
              disabled={creating}
              onClick={() => onCreate(question)}
              className="h-auto justify-start whitespace-normal py-2.5 text-left text-sm"
            >
              {question}
            </Button>
          ))}
        </div>
      </div>
      {error ? (
        <div className="px-4 pb-2 text-center text-sm text-destructive">{error}</div>
      ) : null}
      <ChatInput
        status={creating ? "submitted" : "ready"}
        onSubmit={(text) => onCreate(text)}
        onStop={() => {}}
      />
    </div>
  );
}

export default function ChatPage() {
  const { threadId } = useParams<{ threadId?: string }>();
  const navigate = useNavigate();
  const { threads, refresh } = useThreads();
  const [pendingQuestion, setPendingQuestion] = useState<string>();
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const startNewThread = async (question: string) => {
    setCreating(true);
    setCreateError(null);
    try {
      const thread = await createThread(question.slice(0, 200));
      refresh();
      setPendingQuestion(question);
      navigate(`/chat/${thread.id}`, { replace: true });
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "创建会话失败，请重试");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex h-screen bg-background">
      <ThreadSidebar threads={threads} activeThreadId={threadId} />
      <main className="flex min-w-0 flex-1 flex-col">
        {threadId ? (
          <ChatView
            key={threadId}
            threadId={threadId}
            title={threads.find((thread) => thread.id === threadId)?.title}
            initialQuestion={pendingQuestion}
            onInitialConsumed={() => setPendingQuestion(undefined)}
            onAnswered={refresh}
          />
        ) : (
          <EmptyState
            onCreate={(question) => void startNewThread(question)}
            creating={creating}
            error={createError}
          />
        )}
      </main>
    </div>
  );
}
