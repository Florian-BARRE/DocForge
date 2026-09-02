// ====== Code Summary ======
// One fallback attempt in a chain — "N. name — escalate if score < X or on failure". The last
// step is terminal (its threshold is meaningless: there is nothing left to escalate to), so its
// score input is replaced by a plain "final attempt" label. A NON-scored family (embed/llm/
// structgen) has no threshold at all — its fallback is failure-only, and the compiler silently
// drops any score_below sent for it, so the input is never even offered (see `scored`). Config is
// collapsed by default.

import { useState } from "react";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import { inputStyle } from "../../components/inputStyle";
import type { ChainStep, NodeCard } from "../../api/types";
import { theme } from "../../theme";
import { hasConfigFields } from "../../components/schema-form/paletteLookup";

const iconButton: React.CSSProperties = {
  background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
  color: theme.color.dim, cursor: "pointer", fontSize: theme.font.size.s, padding: "2px 7px",
};

interface ChainStepCardProps {
  step: ChainStep;
  index: number;
  isLast: boolean;
  /** Whether this step's family carries a score a threshold can escalate on — gates the input. */
  scored: boolean;
  card?: NodeCard;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  onConfigChange: (field: string, value: unknown) => void;
  /** Absent for a non-scored chain — the threshold row degrades to a plain failure-only label. */
  onScoreBelowChange?: (value: number | null) => void;
  /** Present only for a chain-owned stage's primary step (parse/embed's step 0) — lets that ONE
   *  representation double as the stage's own provider picker (see `ChainStepList`), instead of a
   *  separate dropdown duplicating it above the chain. Swapping resets the step's config. */
  kindOptions?: { kind: string; label: string }[];
  onKindChange?: (kind: string) => void;
  /** Starts this step's config panel open — used for the primary step above so its config reads
   *  the same as before it was folded into the chain (previously always-visible). */
  defaultExpanded?: boolean;
}

export function ChainStepCard({
  step, index, isLast, scored, card, onMoveUp, onMoveDown, onRemove, onConfigChange, onScoreBelowChange,
  kindOptions, onKindChange, defaultExpanded = false,
}: ChainStepCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const configurable = hasConfigFields(card);

  return (
    <div style={{ background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, padding: theme.space.s }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span
          style={{
            width: 20, height: 20, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center",
            background: theme.color.chainSoft, color: theme.color.chain,
            fontSize: theme.font.size.xs, fontWeight: 700,
          }}
        >
          {index + 1}
        </span>
        {kindOptions && onKindChange ? (
          <select
            value={step.kind}
            onChange={(e) => onKindChange(e.target.value)}
            style={{
              background: theme.color.surface2, color: theme.color.text, border: `1px solid ${theme.color.line}`,
              borderRadius: theme.radius.s, padding: "2px 6px", fontSize: theme.font.size.m, fontWeight: 700,
            }}
          >
            {kindOptions.map((o) => <option key={o.kind} value={o.kind}>{o.label}</option>)}
          </select>
        ) : (
          <strong style={{ fontSize: theme.font.size.m }}>{card?.name ?? step.kind}</strong>
        )}
        <span style={{ flex: 1, color: theme.color.dim, fontSize: theme.font.size.xs }}>{card?.summary}</span>
        <button onClick={onMoveUp} disabled={index === 0} style={iconButton} title="move up">↑</button>
        <button onClick={onMoveDown} disabled={isLast} style={iconButton} title="move down">↓</button>
        {configurable && (
          <button onClick={() => setExpanded((v) => !v)} style={iconButton}>
            {expanded ? "▾" : "▸"} config
          </button>
        )}
        <button onClick={onRemove} style={{ ...iconButton, color: theme.color.error }} title="remove step">✕</button>
      </div>
      <div style={{ marginTop: theme.space.xs, marginLeft: 28, display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.xs, color: theme.color.dim }}>
        {isLast ? (
          <span>final attempt — always accepted, no escalation</span>
        ) : scored ? (
          <>
            <span>escalate to the next step when score &lt;</span>
            <input
              type="number" step="0.05" min={0} max={1}
              value={step.score_below ?? ""}
              placeholder="on failure only"
              onChange={(e) => onScoreBelowChange?.(e.target.value === "" ? null : Number(e.target.value))}
              style={{ ...inputStyle, width: 90, fontFamily: theme.font.mono }}
            />
            <span>or on failure</span>
          </>
        ) : (
          <span>falls through to the next step on failure — no quality threshold for this provider</span>
        )}
      </div>
      {expanded && configurable && card && (
        <div style={{ marginTop: theme.space.s }}>
          <SchemaForm schema={card.config_schema} values={step.config} onChange={onConfigChange} />
        </div>
      )}
    </div>
  );
}
