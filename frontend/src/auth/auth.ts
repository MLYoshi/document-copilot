// Token storage + single-flight refresh. Refreshes go through http.request
// directly (not the api singleton) to avoid circular 401-retry triggers.
import { env } from "@/lib/env";
import { configureAuth } from "@/lib/api";
import { ApiError, request } from "@/lib/http";
import type { TokenPair } from "@/auth/types";

const ACCESS_KEY = "dc.access_token";
const REFRESH_KEY = "dc.refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(pair: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, pair.access_token);
  localStorage.setItem(REFRESH_KEY, pair.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

let refreshInFlight: Promise<string> | null = null;

export function refreshAccessToken(): Promise<string> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doRefresh(): Promise<string> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    clearTokens();
    throw new ApiError("No refresh token available");
  }
  try {
    const pair = await request<TokenPair>(`${env.apiBaseUrl}/auth/refresh`, {
      method: "POST",
      body: { refresh_token: refreshToken },
    });
    setTokens(pair);
    return pair.access_token;
  } catch (error) {
    clearTokens();
    throw error;
  }
}

configureAuth({
  getAccessToken,
  refreshAccessToken,
  onAuthFailure: () => window.location.replace("/login"),
});
