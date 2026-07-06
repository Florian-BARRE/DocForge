// ====== Code Summary ======
// One method of a stackable stage (contextualize) — name/summary, reorder/remove controls, and
// its own config collapsed by default (most methods, like breadcrumb, need no tuning at all).

import { useState } from "react";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import type { NodeCard, StackMethod } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { hasConfigFields } from "./state/paletteLookup";

const iconButton: React.CSSProperties = {
  background: "none", border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
  color: theme.color.dim, cursor: "pointer", fontSize: theme.font.size.s, padding: "1px 6px",
};

interface StackMethodCardProps {
  stageKey: string;
  method: StackMethod;
  index: number;
  isFirst: boolean;
  isLast: boolean;
  card?: NodeCard;
  actions: StageRailActions;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}

export function StackMethodCard({
  stageKey, method, index, isFirst, isLast, card, actions, onMoveUp, onMoveDown, onRemove,
}: StackMethodCardProps) {
  const [expanded, setExpanded] = useState(false);
  const configurable = hasConfigFields(card);

  return (
    <div style={{ background: theme.color.bg, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, padding: theme.space.s }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.s, width: 16, textAlign: "right" }}>{index + 1}.</span>
        <strong style={{ fontSize: theme.font.size.m }}>{card?.name ?? method.kind}</strong>
        <span style={{ flex: 1, color: theme.color.dim, fontSize: theme.font.size.xs }}>{card?.summary}</span>
        <button onClick={onMoveUp} disabled={isFirst} title="move up" style={iconButton}>↑</button>
        <button onClick={onMoveDown} disabled={isLast} title="move down" style={iconButton}>↓</button>
        {configurable && (
          <button onClick={() => setExpanded((v) => !v)} style={iconButton}>
            {expanded ? "▾" : "▸"} config
          </button>
        )}
        <button onClick={onRemove} title="remove" style={{ ...iconButton, color: theme.color.error }}>✕</button>
      </div>
      {expanded && configurable && card && (
        <div style={{ marginTop: theme.space.s }}>
          <SchemaForm
            schema={card.config_schema}
            values={method.config}
            onChange={(field, value) => actions.setStackMethodConfig(stageKey, index, field, value)}
          />
        </div>
      )}
    </div>
  );
}
