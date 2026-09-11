// ====== Code Summary ======
// One column of the failure-breakdown panel — a title and its top buckets, each row clickable to
// jump into All Jobs pre-filtered on that cause (the "why it's breaking, and show me those jobs"
// loop). The "unknown" bucket (a null group key) is never clickable — there is no equivalent filter
// value to pass the API for "field is null".

import { theme } from "../../theme";

export interface BreakdownRow {
  key: string;
  label: string;
  count: number;
}

interface FailureBucketListProps {
  title: string;
  rows: BreakdownRow[];
  onSelect: (key: string) => void;
}

export function FailureBucketList({ title, rows, onSelect }: FailureBucketListProps) {
  return (
    <div style={{ flex: 1, minWidth: 180, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.mute, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {title}
      </div>
      {rows.length === 0 && <div style={{ fontSize: theme.font.size.s, color: theme.color.mute }}>none</div>}
      {rows.map((row) => {
        const clickable = row.label !== "unknown";
        return (
          <div key={row.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s }}>
            {clickable ? (
              <button
                type="button"
                onClick={() => onSelect(row.key)}
                style={{
                  background: "none", border: "none", padding: 0, textAlign: "left", cursor: "pointer",
                  color: theme.color.text, fontSize: theme.font.size.s, textDecoration: "underline", textDecorationColor: theme.color.line,
                }}
              >
                {row.label}
              </button>
            ) : (
              <span style={{ color: theme.color.mute, fontSize: theme.font.size.s, fontStyle: "italic" }}>{row.label}</span>
            )}
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.errorStrong }}>{row.count}</span>
          </div>
        );
      })}
    </div>
  );
}
