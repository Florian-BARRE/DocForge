// ====== Code Summary ======
// Shared fetch plumbing: one error type every feature catches the same way, and a normalizer
// for the several `detail` shapes the backend can return (plain string, FastAPI's own
// loc/msg/type validation errors, or the collections router's own code/location/message list).
// Also owns the API token store — `apiFetch` is the single chokepoint that attaches the Bearer
// header, so every existing `api/*.ts` client gets auth for free.

const TOKEN_STORAGE_KEY = "docforge_api_token";

/** Reads the API token the user pasted in — `null` when unset (dev / auth-off backends). */
export function getApiToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

/** Persists the API token so it survives a reload. */
export function setApiToken(token: string): void {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

/** Drops the stored token — subsequent requests go out unauthenticated again. */
export function clearApiToken(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export interface ApiIssue {
  code?: string;
  location?: string;
  message: string;
}

/** Thrown by every client call below — carries the HTTP status and normalized issues. */
export class HttpError extends Error {
  readonly status: number;
  readonly issues: ApiIssue[];

  constructor(status: number, issues: ApiIssue[]) {
    super(issues.map((i) => i.message).join("; ") || `Request failed (${status})`);
    this.status = status;
    this.issues = issues;
  }
}

/** The backend's several `detail` shapes, flattened into one issue list. */
function normalizeDetail(detail: unknown): ApiIssue[] {
  if (typeof detail === "string") return [{ message: detail }];
  if (Array.isArray(detail))
    return detail.map((entry) => {
      if (typeof entry === "string") return { message: entry };
      const record = entry as Record<string, unknown>;
      // Collections router's own shape: {code, location, message}.
      if (typeof record.message === "string")
        return {
          code: typeof record.code === "string" ? record.code : undefined,
          location: typeof record.location === "string" ? record.location : undefined,
          message: record.message,
        };
      // FastAPI's own validation error shape: {loc, msg, type}.
      if (typeof record.msg === "string")
        return {
          code: typeof record.type === "string" ? record.type : undefined,
          location: Array.isArray(record.loc) ? record.loc.join(".") : undefined,
          message: record.msg,
        };
      return { message: JSON.stringify(entry) };
    });
  if (detail && typeof detail === "object")
    return normalizeDetail([detail]);
  return [];
}

/** JSON request helper: throws HttpError with normalized issues on any non-2xx response. */
export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const token = getApiToken();
  const headers = token
    ? { ...(init?.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` }
    : init?.headers;
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    let issues: ApiIssue[] = [{ message: `Request failed (${response.status})` }];
    try {
      const body = await response.json();
      const normalized = normalizeDetail(body?.detail ?? body);
      if (normalized.length) issues = normalized;
    } catch {
      // Body was not JSON — keep the generic issue.
    }
    throw new HttpError(response.status, issues);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
