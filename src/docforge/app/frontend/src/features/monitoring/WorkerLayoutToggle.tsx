// ====== Code Summary ======
// A compact segmented control switching how the worker-card grid lays out — List (one per row),
// a fixed column count, or Auto (today's `repeat(auto-fill, minmax(320px,1fr))` behavior). Sits at
// the top-right of the Workers page header row. Deliberately its own small control rather than the
// shared SegmentedControl primitive: that one renders a full-width `<legend>` + equal-width grid
// columns sized for wordy option labels, not a dense inline row of 4 short segments.

import { theme } from "../../theme";
import type { WorkersLayout } from "./state/useWorkersLayout";

interface LayoutOption {
  value: WorkersLayout;
  label: string;
}

const OPTIONS: LayoutOption[] = [
  { value: "list", label: "List" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: "auto", label: "Auto" },
];

interface WorkerLayoutToggleProps {
  layout: WorkersLayout;
  onChange: (layout: WorkersLayout) => void;
}

export function WorkerLayoutToggle({ layout, onChange }: WorkerLayoutToggleProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Worker card layout"
      style={{
        display: "inline-flex", gap: 2, padding: 2, flexShrink: 0,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
      }}
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === layout;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={typeof opt.value === "number" ? `${opt.value} columns` : opt.label}
            onClick={() => onChange(opt.value)}
            style={{
              cursor: "pointer", minWidth: 30, padding: `${theme.space.xs}px ${theme.space.s}px`,
              borderRadius: theme.radius.s, border: "none",
              background: active ? theme.color.accentSoft : "transparent",
              color: active ? theme.color.accentSafe : theme.color.mute,
              fontFamily: typeof opt.value === "number" ? theme.font.mono : theme.font.family,
              fontSize: theme.font.size.xs, fontWeight: active ? theme.font.weight.semibold : theme.font.weight.normal,
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
