import { env } from "@/lib/env";
import { ApiError, request } from "@/lib/http";

// Auth hooks are injected by the auth module (src/auth/auth.ts) via
// configureAuth, so this layer stays independent of the auth module.
// The refresh hook must implement single-flight semantics.
type AuthHooks = {
  getAccessToken: () => string | null;
  refreshAccessToken: () => Promise<string>;
  onAuthFailure: () => void;
};

let authHooks: AuthHooks | null = null;

export function configureAuth(hooks: AuthHooks) {
  authHooks = hooks;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  /** Skip bearer injection and 401 refresh retry (auth endpoints themselves). */
  auth?: boolean;
  timeoutMs?: number;
};

async function requestWithAuth<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method, body, auth = true, timeoutMs } = options;
  const url = `${env.apiBaseUrl}${path}`;

  const buildHeaders = (): Record<string, string> => {
    if (!auth) return {};
    const token = authHooks?.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  try {
    return await request<T>(url, { method, body, headers: buildHeaders(), timeoutMs });
  } catch (error) {
    if (
      !auth ||
      authHooks === null ||
      !(error instanceof ApiError) ||
      error.status !== 401
    ) {
      throw error;
    }

    // Access token expired or invalid: try one refresh, then retry once.
    let newToken: string;
    try {
      newToken = await authHooks.refreshAccessToken();
    } catch {
      authHooks.onAuthFailure();
      throw new ApiError("Session expired. Please sign in again.", { status: 401 });
    }

    return await request<T>(url, {
      method,
      body,
      headers: { Authorization: `Bearer ${newToken}` },
      timeoutMs,
    });
  }
}

export const api = {
  get<T>(path: string, options: RequestOptions = {}) {
    return requestWithAuth<T>(path, { method: "GET", ...options });
  },
  post<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return requestWithAuth<T>(path, { method: "POST", body, ...options });
  },
  put<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return requestWithAuth<T>(path, { method: "PUT", body, ...options });
  },
  patch<T>(path: string, body?: unknown, options: RequestOptions = {}) {
    return requestWithAuth<T>(path, { method: "PATCH", body, ...options });
  },
  delete<T>(path: string, options: RequestOptions = {}) {
    return requestWithAuth<T>(path, { method: "DELETE", ...options });
  },
};
