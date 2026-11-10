import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, clearSession, type Message, type Thread, type User } from "@/lib/api";

export function ChatPage({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeThread = threads.find((thread) => thread.id === activeId);

  useEffect(() => {
    api.threads().then(setThreads).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法加载会话"));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function selectThread(id: string) {
    if (sending || id === activeId) return;
    setActiveId(id);
    setLoadingMessages(true);
    setError("");
    try {
      setMessages(await api.messages(id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法加载消息");
    } finally {
      setLoadingMessages(false);
    }
  }

  function newThread() {
    if (sending) return;
    setActiveId(null);
    setMessages([]);
    setError("");
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || sending) return;
    setSending(true);
    setError("");
    setQuestion("");
    let threadId = activeId;
    try {
      if (!threadId) {
        const thread = await api.createThread(text.slice(0, 40));
        threadId = thread.id;
        setThreads((current) => [thread, ...current]);
        setActiveId(thread.id);
      }
      const temporaryId = `temporary-${Date.now()}`;
      setMessages((current) => [
        ...current,
        { id: `${temporaryId}-user`, role: "user", content: text, created_at: new Date().toISOString(), citations: [] },
        { id: `${temporaryId}-assistant`, role: "assistant", content: "", created_at: new Date().toISOString(), citations: [] },
      ]);
      await api.streamMessage(threadId, text, (delta) => {
        setMessages((current) => current.map((message) => message.id === `${temporaryId}-assistant` ? { ...message, content: message.content + delta } : message));
      }, (citations) => {
        setMessages((current) => current.map((message) => message.id === `${temporaryId}-assistant` ? { ...message, citations } : message));
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发送失败，请重试");
      setQuestion((current) => current || text);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function logout() {
    try { await api.logout(); } catch { /* 本地会话仍需清理 */ }
    clearSession();
    onLogout();
  }

  return (
    <div className="flex h-screen bg-slate-50">
      <aside className="hidden w-64 shrink-0 flex-col border-r bg-white md:flex">
        <div className="border-b p-4">
          <h1 className="font-semibold">Document Copilot</h1>
          <p className="mt-1 truncate text-xs text-muted-foreground">{user.email}</p>
        </div>
        <div className="p-3"><Button className="w-full" onClick={newThread} disabled={sending}>＋ 新建会话</Button></div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3" aria-label="历史会话">
          {threads.map((thread) => (
            <button key={thread.id} className={`w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors ${thread.id === activeId ? "bg-secondary font-medium" : "text-muted-foreground hover:bg-secondary"}`} onClick={() => void selectThread(thread.id)} disabled={sending}>
              {thread.title || "未命名会话"}
            </button>
          ))}
          {threads.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">暂无历史会话</p>}
        </nav>
        <div className="border-t p-3"><Button variant="ghost" className="w-full" onClick={() => void logout()}>退出登录</Button></div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b bg-white px-4 md:px-8">
          <div className="min-w-0">
            <h2 className="truncate font-medium">{activeThread?.title || "新会话"}</h2>
            <p className="text-xs text-muted-foreground">回答仅基于已收录的 SEC 披露文件</p>
          </div>
          <Button variant="outline" size="sm" className="md:hidden" onClick={() => void logout()}>退出</Button>
        </header>

        <section className="flex-1 overflow-y-auto" aria-live="polite">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
            {!loadingMessages && messages.length === 0 && (
              <div className="py-20 text-center">
                <h3 className="text-xl font-semibold">今天想了解什么？</h3>
                <p className="mt-3 text-sm text-muted-foreground">例如：Apple 最新年报中提到了哪些主要风险？</p>
              </div>
            )}
            {loadingMessages && <p className="text-center text-sm text-muted-foreground">正在加载消息…</p>}
            {messages.map((message) => (
              <article key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={message.role === "user" ? "max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-primary-foreground" : "max-w-full flex-1"}>
                  {message.role === "assistant" && <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Copilot</p>}
                  <p className="whitespace-pre-wrap text-sm leading-7">{message.content || (sending ? "正在生成回答…" : "")}</p>
                  {message.citations.length > 0 && (
                    <details className="mt-3 border-t pt-2 text-xs text-muted-foreground">
                      <summary className="cursor-pointer">查看 {message.citations.length} 条引用</summary>
                      {message.citations.map((citation) => <blockquote key={citation.passage_id} className="mt-2 border-l-2 pl-3">[{citation.ordinal}] {citation.quote || citation.passage_id}</blockquote>)}
                    </details>
                  )}
                </div>
              </article>
            ))}
            {error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-destructive">{error}</p>}
            <div ref={bottomRef} />
          </div>
        </section>

        <footer className="shrink-0 border-t bg-white p-4">
          <form className="mx-auto flex max-w-3xl items-end gap-2" onSubmit={sendMessage}>
            <Textarea aria-label="输入问题" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={handleKeyDown} placeholder="输入问题，Enter 发送，Shift + Enter 换行" rows={2} maxLength={10000} disabled={sending} />
            <Button className="h-10" disabled={sending || !question.trim()}>{sending ? "回答中…" : "发送"}</Button>
          </form>
        </footer>
      </main>
    </div>
  );
}
