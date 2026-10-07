// ====== Code Summary ======
// The body of the bulk re-ingest dialog: the replay-stage select plus whichever structured refusal
// the last attempt hit (estimate to confirm, unsupported stage, saturated queue). Purely
// presentational — BulkActionBar owns the state and the confirm button.

import type { EstimateRequired, ReplayFrom, ReplayUnsupported } from "../../api/reingest";
import { EstimateRequiredNotice } from "../../components/reingest/EstimateRequiredNotice";
import { ReplayStageSelect } from "../../components/reingest/ReplayStageSelect";
import { ReplayUnsupportedNotice } from "../../components/reingest/ReplayUnsupportedNotice";
import { theme } from "../../theme";

interface BulkReingestChoicesProps {
  replayFrom: ReplayFrom;
  onReplayFromChange: (stage: ReplayFrom) => void;
  pending: boolean;
  estimate: EstimateRequired | null;
  unsupported: ReplayUnsupported | null;
  /** undefined = queue not saturated; null = saturated without a Retry-After; number = seconds. */
  queueRetry: number | null | undefined;
}

export function BulkReingestChoices({
  replayFrom, onReplayFromChange, pending, estimate, unsupported, queueRetry,
}: BulkReingestChoicesProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <ReplayStageSelect
        value={replayFrom}
        onChange={onReplayFromChange}
        allowed={unsupported?.allowed}
        disabled={pending}
      />
      {unsupported && <ReplayUnsupportedNotice issue={unsupported} onPick={onReplayFromChange} />}
      {estimate && <EstimateRequiredNotice info={estimate} />}
      {queueRetry !== undefined && (
        <span role="alert" style={{ color: theme.color.errorStrong, fontSize: theme.font.size.s }}>
          The ingestion queue is full — retry
          {queueRetry !== null ? <> in <span style={{ fontFamily: theme.font.mono }}>{queueRetry} s</span></> : " shortly"}
        </span>
      )}
    </div>
  );
}
