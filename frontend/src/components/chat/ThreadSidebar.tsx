// Left rail: brand + new-chat button, thread history, account footer.
// Sign-out relies on RequireAuth — once useAuth().user is cleared the
// router redirects to /login.
import { LogOut, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import type { Thread } from "@/chat/types";
import { cn } from "@/lib/utils";

function relativeTime(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

type ThreadSidebarProps = {
  threads: Thread[];
  activeThreadId?: string;
};

export function ThreadSidebar({ threads, activeThreadId }: ThreadSidebarProps) {
  const { user, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r bg-card">
      <div className="px-4 py-4">
        <p className="text-base font-semibold tracking-tight">Document Copilot</p>
        <Button asChild className="mt-3 w-full">
          <Link to="/chat">
            <Plus className="size-4" />
            新对话
          </Link>
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1 px-2">
        <nav className="space-y-1 pb-4" aria-label="历史会话">
          {threads.map((thread) => {
            const active = thread.id === activeThreadId;
            return (
              <Link
                key={thread.id}
                to={`/chat/${thread.id}`}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "block rounded-md border-l-[3px] py-2 pl-[9px] pr-3 text-sm transition-colors",
                  active
                    ? "border-primary bg-muted font-medium"
                    : "border-transparent hover:bg-accent"
                )}
              >
                <span className="block truncate">{thread.title || "未命名对话"}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  {relativeTime(thread.updated_at)}
                </span>
              </Link>
            );
          })}
          {threads.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-muted-foreground">
              暂无历史会话
            </p>
          ) : null}
        </nav>
      </ScrollArea>
      <Separator />
      <div className="flex items-center justify-between gap-2 px-4 py-3">
        <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleSignOut}
          disabled={signingOut}
          aria-label="登出"
        >
          <LogOut className="size-4" />
          {signingOut ? "登出中…" : "登出"}
        </Button>
      </div>
    </aside>
  );
}
