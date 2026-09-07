// ====== Code Summary ======
// Status-to-tone mapping for a document's ingestion lifecycle — a local duplicate of
// features/explorer/DocumentStatusChip.tsx (feature slices never cross-import). A DONE row can
// still carry a non-fatal `warning_reason` (e.g. a 0-chunk run) — surfaced as a small warn-toned
// dot ahead of the label, without touching TONE_BY_STATUS (a warning is never a failure).

import type { DocumentStatus } from "../../api/corpus";
import { Chip, type ChipTone } from "../../components/Chip";
import { theme } from "../../theme";

const TONE_BY_STATUS: Record<DocumentStatus, ChipTone> = {
  pending: "warn",
  processing: "accent",
  done: "ok",
  failed: "error",
  cancelled: "skip",
};

interface CorpusStatusChipProps {
  status: DocumentStatus;
  /** True when the row carries a non-fatal `warning_reason` (e.g. a 0-chunk run). */
  hasWarning?: boolean;
}

export function CorpusStatusChip({ status, hasWarning }: CorpusStatusChipProps) {
  return (
    <Chip tone={TONE_BY_STATUS[status] ?? "dim"} title={hasWarning ? "Completed with a warning" : undefined}>
      {hasWarning && (
        <span
          aria-hidden="true"
          style={{ display: "inline-block", width: 6, height: 6, borderRadius: theme.radius.pill, background: theme.color.warnStrong, marginRight: 5 }}
        />
      )}
      {status}
    </Chip>
  );
}
