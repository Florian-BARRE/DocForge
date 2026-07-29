// ====== Code Summary ======
// The wizard's horizontal step indicator — numbered circles joined by a line; done steps fill
// accent, the current step outlines accent, future steps stay dim. Purely presentational.

import { theme as t } from "../../../theme";

export function WizardSteps({ labels, current }: { labels: string[]; current: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: t.space.xl }}>
      {labels.map((label, index) => {
        const done = index < current;
        const active = index === current;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", flex: index < labels.length - 1 ? 1 : "0 0 auto" }}>
            <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexShrink: 0 }}>
              <span
                style={{
                  width: 26, height: 26, borderRadius: t.radius.pill, display: "grid", placeItems: "center",
                  fontSize: t.font.size.s, fontWeight: t.font.weight.semibold, flexShrink: 0,
                  background: done || active ? t.color.accent : t.color.surface2,
                  color: done || active ? t.color.onAccent : t.color.dim,
                  border: `1px solid ${done || active ? t.color.accent : t.color.line}`,
                }}
              >
                {done ? "✓" : index + 1}
              </span>
              <span style={{ fontSize: t.font.size.m, fontWeight: active ? t.font.weight.semibold : t.font.weight.normal, color: active ? t.color.text : t.color.dim, whiteSpace: "nowrap" }}>
                {label}
              </span>
            </div>
            {index < labels.length - 1 && (
              <div style={{ flex: 1, height: 1, background: done ? t.color.accent : t.color.line, margin: `0 ${t.space.m}px` }} />
            )}
          </div>
        );
      })}
    </div>
  );
}
