// ====== Code Summary ======
// One vertical entry of the search rail: step number + node identity (from the palette card),
// its config form when the node has knobs, or a "read-only step" hint when it doesn't (encode/
// hydrate/deliver today) — mirrors the ingestion StageCard's presentation with the theme tokens.

import { Chip } from "../../components/Chip";
import { findNodeCard, hasConfigFields } from "../../components/schema-form/paletteLookup";
import type { ActionBlob, Palette } from "../../api/types";
import { theme } from "../../theme";
import { NodeConfigForm } from "./NodeConfigForm";

interface SearchNodeCardProps {
  step: number;
  node: ActionBlob;
  palette: Palette;
  onChangeConfig: (field: string, value: unknown) => void;
}

export function SearchNodeCard({ step, node, palette, onChangeConfig }: SearchNodeCardProps) {
  const card = findNodeCard(palette, node.family, node.kind);
  const configurable = hasConfigFields(card);

  return (
    <div
      style={{
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
        display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.m }}>
        <span
          style={{
            width: 22, height: 22, flexShrink: 0, borderRadius: "50%",
            background: theme.color.accentSoft, color: theme.color.accent,
            fontSize: theme.font.size.s, display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {step}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
            <strong style={{ fontSize: theme.font.size.l }}>{card?.name ?? node.kind}</strong>
            <Chip tone="dim">{node.family}</Chip>
            {!configurable && <Chip tone="dim">read-only</Chip>}
          </div>
          {card?.summary && <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{card.summary}</div>}
        </div>
      </div>

      {configurable && (
        <div style={{ paddingLeft: 22 + theme.space.m }}>
          <NodeConfigForm node={node} palette={palette} onChange={onChangeConfig} />
        </div>
      )}
    </div>
  );
}
