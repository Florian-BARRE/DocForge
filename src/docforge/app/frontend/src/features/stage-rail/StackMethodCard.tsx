// ====== Code Summary ======
// One method of a stackable stage (contextualize) — name/summary, reorder/remove controls, its own
// config collapsed by default (most methods, like breadcrumb, need no tuning at all), and — for the
// `llm` method only — its OWN nested fallback chain (StackMethodChainSection), the subtlest chain
// surface in the rail.

import { useState } from "react";
import { SchemaForm } from "../../components/schema-form/SchemaForm";
import type { ChainView, NodeCard, Palette, StackMethod } from "../../api/types";
import { theme } from "../../theme";
import type { StageRailActions } from "./actions";
import { StackMethodChainSection } from "./StackMethodChainSection";
import { hasConfigFields } from "../../components/schema-form/paletteLookup";

const iconButton: React.CSSProperties = {
  background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
  color: theme.color.dim, cursor: "pointer", fontSize: theme.font.size.s, padding: "2px 7px",
};

interface StackMethodCardProps {
  stageKey: string;
  method: StackMethod;
  index: number;
  isFirst: boolean;
  isLast: boolean;
  card?: NodeCard;
  /** The `contextualize.{index}` chain view the backend surfaces for the `llm` method — present
   *  iff `method.kind === "llm"`. */
  chainView?: ChainView;
  palette: Palette;
  actions: StageRailActions;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
}

export function StackMethodCard({
  stageKey, method, index, isFirst, isLast, card, chainView, palette, actions, onMoveUp, onMoveDown, onRemove,
}: StackMethodCardProps) {
  const [expanded, setExpanded] = useState(false);
  const configurable = hasConfigFields(card);

  return (
    <div style={{ background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, padding: theme.space.s }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span
          style={{
            width: 20, height: 20, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center",
            background: theme.color.surface3, color: theme.color.dim,
            fontSize: theme.font.size.xs, fontWeight: 700,
          }}
        >
          {index + 1}
        </span>
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
      {chainView && (
        <StackMethodChainSection
          stageKey={stageKey} methodIndex={index} chainView={chainView} palette={palette} actions={actions}
        />
      )}
    </div>
  );
}
