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
  background: "none", border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
  color: theme.color.dim, cursor: "pointer", fontSize: theme.font.size.s, padding: "1px 6px",
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
}

export function ChainStepCard({
  step, index, isLast, scored, card, onMoveUp, onMoveDown, onRemove, onConfigChange, onScoreBelowChange,
}: ChainStepCardProps) {
  const [expanded, setExpanded] = useState(false);
  const configurable = hasConfigFields(card);

  return (
    <div style={{ background: theme.color.card, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s, padding: theme.space.s }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ color: theme.color.chain, fontWeight: 700, fontSize: theme.font.size.s, width: 16, textAlign: "right" }}>{index + 1}.</span>
        <strong style={{ fontSize: theme.font.size.m }}>{card?.name ?? step.kind}</strong>
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
      <div style={{ marginTop: theme.space.xs, display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.xs, color: theme.color.dim }}>
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
              style={{ ...inputStyle, width: 90 }}
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
