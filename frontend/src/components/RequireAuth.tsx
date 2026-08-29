import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";

// Route guard: waits for the mount-time session probe before deciding,
// so a refresh with valid tokens never flashes the login page.
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, initializing } = useAuth();

  if (initializing) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        加载中…
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return children;
}
