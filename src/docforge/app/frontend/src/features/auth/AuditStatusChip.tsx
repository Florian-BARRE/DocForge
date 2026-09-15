// ====== Code Summary ======
// The audit table's status-code pill — one status ink per outcome class (2xx ok, 4xx warn, 5xx
// error), never orange (that's reserved for the one active/primary thing per brand.md).

import { Chip, type ChipTone } from "../../components/Chip";

function toneForStatus(statusCode: number): ChipTone {
  if (statusCode >= 500) return "error";
  if (statusCode >= 400) return "warn";
  if (statusCode >= 200 && statusCode < 300) return "ok";
  return "neutral";
}

export function AuditStatusChip({ statusCode }: { statusCode: number }) {
  return <Chip tone={toneForStatus(statusCode)}>{statusCode}</Chip>;
}
