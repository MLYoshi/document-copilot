import { useState } from "react";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function HomePage() {
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
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Document Copilot</CardTitle>
          <CardDescription>你已登录</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">
            当前账户：<span className="font-medium">{user?.email}</span>
          </p>
          <Button variant="outline" className="w-full" onClick={handleSignOut} disabled={signingOut}>
            {signingOut ? "登出中…" : "登出"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
