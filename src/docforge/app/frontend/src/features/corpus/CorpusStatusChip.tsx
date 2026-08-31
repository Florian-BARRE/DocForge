// ====== Code Summary ======
// Status-to-tone mapping for a document's ingestion lifecycle — a local duplicate of
// features/explorer/DocumentStatusChip.tsx (feature slices never cross-import).

import type { DocumentStatus } from "../../api/corpus";
import { Chip, type ChipTone } from "../../components/Chip";

const TONE_BY_STATUS: Record<DocumentStatus, ChipTone> = {
  pending: "warn",
  processing: "accent",
  done: "ok",
  failed: "error",
};

export function CorpusStatusChip({ status }: { status: DocumentStatus }) {
  return <Chip tone={TONE_BY_STATUS[status] ?? "dim"}>{status}</Chip>;
}
