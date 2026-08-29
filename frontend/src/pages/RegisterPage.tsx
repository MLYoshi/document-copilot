import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/http";

// Backend constraints: password >= 8 chars and <= 72 bytes (bcrypt limit).
const MIN_PASSWORD_LENGTH = 8;
const MAX_PASSWORD_LENGTH = 72;

function validatePassword(password: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return "密码至少 8 个字符";
  if (password.length > MAX_PASSWORD_LENGTH) return "密码最多 72 个字符";
  return null;
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isNetworkError) return "网络连接失败，请稍后重试";
    return error.detail ?? error.message;
  }
  return "发生未知错误，请重试";
}

export default function RegisterPage() {
  const { signUp } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    setError(null);
    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    setSubmitting(true);
    try {
      await signUp({ email, password });
      setRegisteredEmail(email);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        {registeredEmail ? (
          <>
            <CardHeader>
              <CardTitle className="text-xl">注册成功</CardTitle>
              <CardDescription>账户 {registeredEmail} 已创建，请前往登录页登录。</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild className="w-full">
                <Link to="/login">去登录</Link>
              </Button>
            </CardContent>
          </>
        ) : (
          <>
            <CardHeader>
              <CardTitle className="text-xl">创建账户</CardTitle>
              <CardDescription>注册后即可开始使用 Document Copilot</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">邮箱</Label>
                  <Input id="email" name="email" type="email" required autoComplete="email" placeholder="you@example.com" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">密码</Label>
                  <Input id="password" name="password" type="password" required autoComplete="new-password" />
                  <p className="text-xs text-muted-foreground">密码需为 8–72 个字符</p>
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "注册中…" : "注册"}
                </Button>
              </form>
              <p className="mt-4 text-center text-sm text-muted-foreground">
                已有账户？{" "}
                <Link to="/login" className="underline underline-offset-4 hover:text-foreground">
                  登录
                </Link>
              </p>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
