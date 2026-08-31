// ====== Code Summary ======
// TypeScript mirror of the collection transfer (export/import) REST contract + its typed client.
// Shapes copied verbatim from the backend's Pydantic models
// (app/backend/routers/transfers/models.py) — nothing invented. The download helper mirrors
// api/blobs.ts: the route is authenticated, so a plain <a href> can't carry the Bearer header —
// the bytes are fetched behind auth and saved via an object URL instead.

import { apiFetch, apiFetchBlob } from "./http";

const COLLECTIONS_BASE = "/api/v1/collections";
const TRANSFERS_BASE = "/api/v1/transfers";

export type TransferKind = "export" | "import";
export type TransferStatusValue = "pending" | "running" | "done" | "failed" | string;

/** The 202 envelope returned the instant a transfer is created and enqueued. */
export interface TransferAccepted {
  transfer_id: string;
  kind: TransferKind;
  status: TransferStatusValue;
}

/** The full poll model of a collection transfer — its live status and (when done) its artifact. */
export interface TransferStatus {
  transfer_id: string;
  kind: TransferKind;
  status: TransferStatusValue;
  progress: number;
  stage: string | null;
  counts: Record<string, unknown> | null;
  error: string | null;
  /** Export: the source collection. Import: the new collection once done (null while in flight). */
  collection_id: string | null;
  collection_name: string | null;
  /** The produced bundle's size, in bytes — done export only. */
  size_bytes: number | null;
  format_version: number | null;
  dense_dim: number | null;
  /** When a produced bundle may be garbage-collected — done export only. */
  expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Open an asynchronous export of a whole collection into a portable `.dcexport` bundle. */
export function exportCollection(collectionId: string): Promise<TransferAccepted> {
  return apiFetch(`${COLLECTIONS_BASE}/${collectionId}/export`, { method: "POST" });
}

/** Import a `.dcexport` bundle as a brand-new collection (multipart upload). */
export function importCollection(file: File, targetName?: string): Promise<TransferAccepted> {
  const form = new FormData();
  form.append("file", file);
  if (targetName) form.append("target_name", targetName);
  return apiFetch(`${COLLECTIONS_BASE}/import`, { method: "POST", body: form });
}

/** Poll one transfer's live status — progress, stage, counts, error, and (when done) its artifact. */
export function getTransfer(transferId: string): Promise<TransferStatus> {
  return apiFetch(`${TRANSFERS_BASE}/${transferId}`);
}

/** Fetch a completed export bundle (authenticated) and trigger a browser download under `filename`. */
export async function downloadTransfer(transferId: string, filename: string): Promise<void> {
  const blob = await apiFetchBlob(`${TRANSFERS_BASE}/${transferId}/download`);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
