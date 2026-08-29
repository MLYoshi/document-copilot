// Thin fetch wrapper: JSON in/out, timeout, and a typed ApiError that
// distinguishes network/CORS failures from HTTP error responses.

export class ApiError extends Error {
  readonly status?: number;
  readonly isNetworkError: boolean;
  readonly detail?: string;

  constructor(message: string, options: { status?: number; isNetworkError?: boolean; detail?: string } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.isNetworkError = options.isNetworkError ?? false;
    this.detail = options.detail;
  }
}

const DEFAULT_TIMEOUT_MS = 15_000;

type RequestOptions = {
  method?: string;
  headers?: Record<string, string>;
  body?: unknown;
  timeoutMs?: number;
};

function extractDetail(payload: unknown): string | undefined {
  if (typeof payload !== "object" || payload === null) return undefined;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors come as a list of {loc, msg} objects.
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : undefined))
      .filter((msg): msg is string => typeof msg === "string");
    return messages.join("; ");
  }
  return undefined;
}

export async function request<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", headers = {}, body, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    if (aborted) {
      throw new ApiError(`Request timed out after ${timeoutMs}ms`, { isNetworkError: true });
    }
    throw new ApiError("Network request failed", { isNetworkError: true });
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => undefined);
    const detail = extractDetail(payload);
    throw new ApiError(detail ?? `Request failed with status ${response.status}`, {
      status: response.status,
      detail,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
