const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const ACCESS_TOKEN_KEY = "document_copilot_access_token";
const REFRESH_TOKEN_KEY = "document_copilot_refresh_token";

export interface User { id: string; email: string }
export interface Thread { id: string; title: string; created_at: string; updated_at: string }
export interface Citation { passage_id: string; ordinal: number; quote: string | null }
export interface Message { id: string; role: "user" | "assistant"; content: string; created_at: string; citations: Citation[] }
interface TokenPair { access_token: string; refresh_token: string; token_type: string }
interface StreamEvent { type: "text-delta" | "citations" | "error" | "finish"; delta?: string; citations?: Citation[]; message?: string }

let accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
let refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
let refreshing: Promise<boolean> | null = null;

export function hasSession() {
  return Boolean(accessToken && refreshToken);
}

function saveTokens(tokens: TokenPair) {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearSession() {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function sessionExpired() {
  clearSession();
  window.dispatchEvent(new Event("auth:expired"));
}

async function errorMessage(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string | Array<{ msg: string }> };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join("；");
  } catch { /* 非 JSON 响应 */ }
  return `请求失败（${response.status}）`;
}

async function tryRefresh() {
  if (!refreshToken) return false;
  refreshing ??= fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).then(async (response) => {
    if (!response.ok) return false;
    saveTokens((await response.json()) as TokenPair);
    return true;
  }).catch(() => false).finally(() => { refreshing = null; });
  return refreshing;
}

async function authorizedFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (response.status !== 401 || !retry) return response;
  if (await tryRefresh()) return authorizedFetch(path, init, false);
  sessionExpired();
  return response;
}

async function request<T>(path: string, init: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = authenticated
    ? await authorizedFetch(path, { ...init, headers })
    : await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  login: async (email: string, password: string) => {
    const tokens = await request<TokenPair>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false);
    saveTokens(tokens);
  },
  register: (email: string, password: string) => request<User>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }, false),
  me: () => request<User>("/auth/me"),
  logout: async () => {
    if (!refreshToken) return;
    await request<void>("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
  },
  threads: () => request<Thread[]>("/threads"),
  createThread: (title: string) => request<Thread>("/threads", { method: "POST", body: JSON.stringify({ title }) }),
  messages: (threadId: string) => request<Message[]>(`/threads/${threadId}/messages`),
  streamMessage: async (threadId: string, question: string, onDelta: (text: string) => void, onCitations: (citations: Citation[]) => void) => {
    const response = await authorizedFetch(`/threads/${threadId}/messages/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    if (!response.body) throw new Error("浏览器不支持流式响应");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const data = block.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
        if (!data) continue;
        const event = JSON.parse(data) as StreamEvent;
        if (event.type === "text-delta" && event.delta) onDelta(event.delta);
        if (event.type === "citations" && event.citations) onCitations(event.citations);
        if (event.type === "error") throw new Error(event.message ?? "回答生成失败，请重试");
      }
    }
  },
};
