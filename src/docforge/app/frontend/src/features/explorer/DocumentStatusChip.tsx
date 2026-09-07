// ====== Code Summary ======
// Status-to-tone mapping for a document's ingestion lifecycle — mirrors the monitoring feature's
// JobStatusChip pattern, kept local since a document's own status enum is distinct from a job's.
// A DONE document can still carry a non-fatal `warning_reason` (e.g. a 0-chunk run) — surfaced as a
// small warn-toned dot ahead of the label so it reads as "done, but look closer" without touching
// TONE_BY_STATUS (a warning is never a failure, so the chip itself stays the "ok" tone).

import type { DocumentStatus } from "../../api/explorer";
import { Chip, type ChipTone } from "../../components/Chip";
import { theme } from "../../theme";

const TONE_BY_STATUS: Record<DocumentStatus, ChipTone> = {
  pending: "warn",
  processing: "accent",
  done: "ok",
  failed: "error",
  cancelled: "skip",
};

interface DocumentStatusChipProps {
  status: DocumentStatus;
  /** True when the document carries a non-fatal `warning_reason` (e.g. a 0-chunk run). */
  hasWarning?: boolean;
}

export function DocumentStatusChip({ status, hasWarning }: DocumentStatusChipProps) {
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
