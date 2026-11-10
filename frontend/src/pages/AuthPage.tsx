import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, type User } from "@/lib/api";

export function AuthPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (registering) {
        await api.register(email, password);
        setRegistering(false);
        setPassword("");
        setNotice("注册成功，请登录。若已开启邮箱确认，请先查收确认邮件。");
      } else {
        await api.login(email, password);
        onLogin(await api.me());
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <Card className="w-full max-w-sm p-8">
        <div className="mb-8">
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-500">Driftwood Capital</p>
          <h1 className="text-2xl font-semibold tracking-tight">Document Copilot</h1>
          <p className="mt-2 text-sm text-muted-foreground">查询 SEC 文件，获取有据可依的答案。</p>
        </div>
        <form className="space-y-4" onSubmit={submit}>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="email">邮箱</label>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="password">密码</label>
            <Input id="password" type="password" autoComplete={registering ? "new-password" : "current-password"} required minLength={registering ? 8 : undefined} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={registering ? "至少 8 位" : "请输入密码"} />
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {notice && <p className="text-sm text-green-700">{notice}</p>}
          <Button className="w-full" disabled={busy}>{busy ? "请稍候…" : registering ? "注册" : "登录"}</Button>
        </form>
        <Button variant="ghost" className="mt-3 w-full" onClick={() => { setRegistering((value) => !value); setError(""); setNotice(""); }}>
          {registering ? "已有账号？返回登录" : "没有账号？创建账号"}
        </Button>
      </Card>
    </main>
  );
}
