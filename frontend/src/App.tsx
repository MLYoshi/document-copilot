import { useEffect, useState } from "react";
import { api, clearSession, hasSession, type User } from "@/lib/api";
import { AuthPage } from "@/pages/AuthPage";
import { ChatPage } from "@/pages/ChatPage";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(hasSession());

  useEffect(() => {
    const expire = () => { setUser(null); setChecking(false); };
    window.addEventListener("auth:expired", expire);
    if (hasSession()) {
      api.me().then(setUser).catch(() => clearSession()).finally(() => setChecking(false));
    }
    return () => window.removeEventListener("auth:expired", expire);
  }, []);

  if (checking) return <main className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">正在恢复会话…</main>;
  return user ? <ChatPage user={user} onLogout={() => setUser(null)} /> : <AuthPage onLogin={setUser} />;
}
