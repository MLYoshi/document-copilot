// Thin wrappers over the api singleton for the backend auth endpoints.
import { api } from "@/lib/api";
import type { CredentialsPayload, TokenPair, UserPublic } from "@/auth/types";

// auth: false — these endpoints take no Bearer token, and a 401 from them
// (e.g. wrong password) must never trigger the refresh-and-retry logic.
export function register(payload: CredentialsPayload): Promise<UserPublic> {
  return api.post<UserPublic>("/auth/register", payload, { auth: false });
}

export function login(payload: CredentialsPayload): Promise<TokenPair> {
  return api.post<TokenPair>("/auth/login", payload, { auth: false });
}

export function refresh(refreshToken: string): Promise<TokenPair> {
  return api.post<TokenPair>("/auth/refresh", { refresh_token: refreshToken }, { auth: false });
}

// Requires Bearer access token + refresh_token in the body; returns 204.
export function logout(refreshToken: string): Promise<void> {
  return api.post<void>("/auth/logout", { refresh_token: refreshToken });
}

export function me(): Promise<UserPublic> {
  return api.get<UserPublic>("/auth/me");
}
