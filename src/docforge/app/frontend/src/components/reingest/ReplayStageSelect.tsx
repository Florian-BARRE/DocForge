// ====== Code Summary ======
// "Replay from stage" choice shared by every reingest surface: the default option is a full
// re-ingest (value ""), the others replay only that post-IR stage and its downstream on the
// persisted IR. When the server has answered `replay_unsupported`, `allowed` narrows the offer.

import { REPLAY_STAGES, type ReplayFrom } from "../../api/reingest";
import { inputStyle } from "../inputStyle";

interface ReplayStageSelectProps {
  value: ReplayFrom;
  onChange: (value: ReplayFrom) => void;
  /** Stages the pipeline allows (from a 422); defaults to every replayable stage. */
  allowed?: string[];
  disabled?: boolean;
  /** Fit in a header action cluster instead of a full-width form row. */
  compact?: boolean;
}

export function ReplayStageSelect({ value, onChange, allowed, disabled, compact }: ReplayStageSelectProps) {
  const stages = allowed && allowed.length > 0 ? allowed : [...REPLAY_STAGES];
  // A selection that fell out of the allowed list must stay visible rather than silently flip.
  const options = value && !stages.includes(value) ? [value, ...stages] : stages;
  return (
    <select
      aria-label="Replay from stage"
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
      style={compact ? { ...inputStyle, width: "auto", padding: "6px 8px" } : inputStyle}
    >
      <option value="">Full re-ingest</option>
      {options.map((stage) => (
        <option key={stage} value={stage}>Replay from {stage}</option>
      ))}
    </select>
  );
}
