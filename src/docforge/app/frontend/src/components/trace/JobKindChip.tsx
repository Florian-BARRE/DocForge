// ====== Code Summary ======
// Quiet outline pill naming what a job tracks ("ingestion" / "metadata sync"). Chrome, not status:
// the dim tone keeps orange reserved for the active thing.

import { jobKindLabel, type JobKindValue } from "../../api/jobs";
import { Chip } from "../Chip";

export function JobKindChip({ kind }: { kind: JobKindValue }) {
  return <Chip tone="dim" title={`Job kind: ${kind}`}>{jobKindLabel(kind)}</Chip>;
}
