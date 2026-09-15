// ====== Code Summary ======
// TypeScript mirror of the audit-trail read REST contract + its typed client. Shapes copied
// verbatim from the backend's Pydantic models (AuditEntry/AuditPage) — nothing invented. Keyset
// (not offset) paginated: pass a previous page's `next_cursor` back as `cursor` to fetch the next
// page; `next_cursor: null` means the trail is exhausted. Root/full-access only — a collection-
// scoped key gets a 403 (see AuditTab's handling of that).

import { apiFetch } from "./http";

const BASE = "/api/v1/audit";

/** One immutable audit-trail row — who did what mutating action, to what, and the outcome. */
export interface AuditEntry {
  id: number;
  created_at: string;
  method: string;
  /** The matched route TEMPLATE, never the raw concrete path with ids. */
  path: string;
  status_code: number;
  actor_user_id: string | null;
  actor_key_id: string | null;
  /** Human-readable actor label (key name / username / "root"). */
  actor_label: string | null;
  target_type: string | null;
  target_id: string | null;
  correlation_id: string | null;
  /** The XFF-aware client ip. */
  client_ip: string | null;
}

/** One newest-first, keyset-paginated page of the audit trail. */
export interface AuditPage {
  entries: AuditEntry[];
  limit: number;
  /** Opaque cursor for the next page, or null when the trail is exhausted. */
  next_cursor: string | null;
}

export interface ListAuditParams {
  limit?: number;
  /** Opaque cursor from a previous page's `next_cursor`. */
  cursor?: string;
}

export function listAudit(params: ListAuditParams = {}): Promise<AuditPage> {
  const query = new URLSearchParams();
  if (params.limit !== undefined) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const qs = query.toString();
  return apiFetch(`${BASE}${qs ? `?${qs}` : ""}`);
}
