// ====== Code Summary ======
// The "why is it breaking" panel — top failure causes, grouped by error class / stage / collection,
// over a rolling window (`GET /jobs/failures/breakdown`). Fills the SRE persona's "no failure-cause
// rollup" gap: five same-root failures now read as one bucket of five, not five unrelated rows.

import { theme } from "../../theme";
import { FailureBucketList, type BreakdownRow } from "./FailureBucketList";
import { useFailureBreakdown } from "./state/useFailureBreakdown";

interface FailureBreakdownPanelProps {
  windowHours: number;
  onSelectErrorType: (errorType: string) => void;
  onSelectStage: (stage: string) => void;
  onSelectCollection: (collectionId: string) => void;
}

export function FailureBreakdownPanel({ windowHours, onSelectErrorType, onSelectStage, onSelectCollection }: FailureBreakdownPanelProps) {
  const { data, error } = useFailureBreakdown(windowHours);

  if (error) return <div style={{ color: theme.color.error, fontSize: theme.font.size.s, marginBottom: theme.space.l }}>{error}</div>;
  if (!data) return null;

  const byErrorType: BreakdownRow[] = data.by_error_type.map((b) => ({ key: b.label, label: b.label, count: b.count }));
  const byStage: BreakdownRow[] = data.by_stage.map((b) => ({ key: b.label, label: b.label, count: b.count }));
  const byCollection: BreakdownRow[] = data.by_collection.map((b) => ({
    key: b.collection_id, label: b.collection_name ?? "unknown", count: b.count,
  }));

  return (
    <div
      style={{
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l, background: theme.color.surface,
        padding: theme.space.l, marginBottom: theme.space.l, display: "flex", flexDirection: "column", gap: theme.space.m,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l, color: theme.color.text }}>
          Failure breakdown
        </span>
        <span style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>last {data.window_hours}h</span>
      </div>
      {data.total_failed === 0 ? (
        <div style={{ color: theme.color.okStrong, fontSize: theme.font.size.s }}>No failures in this window.</div>
      ) : (
        <>
          <div style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
            <span style={{ fontFamily: theme.font.mono, color: theme.color.errorStrong, fontWeight: theme.font.weight.semibold }}>{data.total_failed}</span> failed jobs
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l }}>
            <FailureBucketList title="By cause" rows={byErrorType} onSelect={onSelectErrorType} />
            <FailureBucketList title="By stage" rows={byStage} onSelect={onSelectStage} />
            <FailureBucketList title="By collection" rows={byCollection} onSelect={onSelectCollection} />
          </div>
        </>
      )}
    </div>
  );
}
