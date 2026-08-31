// ====== Code Summary ======
// Status-to-tone mapping for a document's ingestion lifecycle — mirrors the monitoring feature's
// JobStatusChip pattern, kept local since a document's own status enum is distinct from a job's.

import { Chip, type ChipTone } from "../../components/Chip";
import type { DocumentStatus } from "../../api/explorer";

const TONE_BY_STATUS: Record<DocumentStatus, ChipTone> = {
  pending: "warn",
  processing: "accent",
  done: "ok",
  failed: "error",
  cancelled: "skip",
};

export function DocumentStatusChip({ status }: { status: DocumentStatus }) {
  return <Chip tone={TONE_BY_STATUS[status] ?? "dim"}>{status}</Chip>;
}
