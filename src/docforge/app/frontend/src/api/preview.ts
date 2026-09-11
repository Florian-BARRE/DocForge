// ====== Code Summary ======
// TypeScript mirror of the pipeline dry-run/preview contract (worker-side async job + its poll) +
// the typed client. Source is XOR: an existing `document_id` OR an uploaded `file` — the caller picks
// one branch of `SubmitPreviewJobArgs`. `blob` is the optional CANDIDATE pipeline (e.g. the stage
// rail's current, possibly unsaved, edit) — omitted, the collection's own stored pipeline is used.

import { apiFetch } from "./http";
import type { GroupBlob } from "./types";

const BASE = "/api/v1/collections";

/** A compact summary of the canonical IR a dry-run produced (the full IR is never returned). */
export interface PreviewIrSummary {
  title: string;
  language: string;
  page_count: number;
  source_format: string;
  file_size: number;
  source_hash: string;
  block_count: number;
  block_type_counts: Record<string, number>;
  figure_count: number;
}

/** One previewed retrieval unit — text truncated to the preview ceiling, never the full chunk. */
export interface PreviewChunk {
  chunk_id: string;
  ordinal: number;
  role: string;
  heading_path: string[];
  token_count: number;
  page_start: number;
  page_end: number;
  text: string;
  text_truncated: boolean;
  context: string;
  generated_meta: Record<string, unknown>;
}

/** The dry-run's ACTUAL metered spend on this one document, priced against the collection's rates. */
export interface PreviewCost {
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number | null;
  priced_call_count: number;
}

/** One node of the execution trace, flattened to materialized-path coordinates (no raw payloads). */
export interface PreviewTraceNode {
  node_id: string;
  kind: string;
  status: string;
  duration_ms: number;
  depth: number;
  node_path: string;
  parent_path: string | null;
  item_index: number | null;
  score: number | null;
  error_type: string | null;
  error_message: string | null;
}

/** The bounded dry-run report — what an ingestion WOULD produce on one document, nothing persisted. */
export interface PreviewResponse {
  ok: boolean;
  source_filename: string;
  ir: PreviewIrSummary | null;
  chunk_count: number;
  chunks: PreviewChunk[];
  chunks_truncated: boolean;
  vector_set_count: number;
  cost: PreviewCost;
  trace: PreviewTraceNode[];
  warnings: string[];
  failed_node_id: string | null;
  failed_node_kind: string | null;
  error: string | null;
}

export type PreviewJobStatus = "pending" | "running" | "done" | "failed";

/** Acknowledgement of an asynchronous (worker-side) dry-run preview submission. */
export interface PreviewJobAccepted {
  preview_id: string;
  status: string;
}

/** A poll of an asynchronous dry-run preview — its coarse status plus the report once complete. */
export interface PreviewJobResult {
  preview_id: string;
  status: PreviewJobStatus;
  result: PreviewResponse | null;
  error: string | null;
}

/** Exactly one of `documentId` / `file` must be set — the source XOR the backend itself enforces. */
export type SubmitPreviewJobArgs = {
  collectionId: string;
  blob?: GroupBlob;
  maxChunks?: number;
} & ({ documentId: string; file?: never } | { file: File; documentId?: never });

/** Submit a worker-side dry-run preview — returns a pollable id, persists NOTHING. Covers every
 *  pipeline (including docling, whose deps live only in the worker image, unlike the inline
 *  `/pipeline/preview` fast-lane). */
export function submitPreviewJob(args: SubmitPreviewJobArgs): Promise<PreviewJobAccepted> {
  const form = new FormData();
  if (args.file) form.append("file", args.file);
  if (args.documentId) form.append("document_id", args.documentId);
  if (args.blob) form.append("blob", JSON.stringify(args.blob));
  if (args.maxChunks !== undefined) form.append("max_chunks", String(args.maxChunks));
  return apiFetch(`${BASE}/${args.collectionId}/pipeline/preview/jobs`, { method: "POST", body: form });
}

/** Poll an asynchronous dry-run preview by its id — the bounded report appears once status is 'done'. */
export function getPreviewJob(collectionId: string, previewId: string): Promise<PreviewJobResult> {
  return apiFetch(`${BASE}/${collectionId}/pipeline/preview/jobs/${previewId}`);
}
