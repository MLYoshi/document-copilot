import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { login, logout, me, register } from "@/auth/api";
import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "@/auth/auth";
import type { CredentialsPayload, UserPublic } from "@/auth/types";

interface AuthContextValue {
  user: UserPublic | null;
  initializing: boolean; // true while the mount-time session probe is running
  signIn: (payload: CredentialsPayload) => Promise<void>;
  signUp: (payload: CredentialsPayload) => Promise<UserPublic>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  // Only a stored token triggers the mount-time session probe; without one
  // there is nothing to initialize.
  const [initializing, setInitializing] = useState<boolean>(() => !!getAccessToken());

  useEffect(() => {
    if (!getAccessToken()) return;
    // Session probe: a 401 here means the stored tokens are unusable.
    me()
      .then(setUser)
      .catch(() => {
        clearTokens();
        setUser(null);
      })
      .finally(() => setInitializing(false));
  }, []);

  const signIn = async (payload: CredentialsPayload) => {
    const pair = await login(payload);
    setTokens(pair);
    setUser(await me());
  };

  const signUp = (payload: CredentialsPayload) => register(payload);

  const signOut = async () => {
    try {
      const refreshToken = getRefreshToken();
      if (refreshToken) await logout(refreshToken);
    } catch {
      // Server-side revocation failed (expired token, network error, etc.) —
      // local sign-out must proceed regardless.
    }
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, initializing, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
