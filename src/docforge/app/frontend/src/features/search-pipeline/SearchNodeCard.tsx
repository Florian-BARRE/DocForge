// ====== Code Summary ======
// One step of the search rail, drawn in the shared SearchStageFrame (the ingestion StageCard's
// shape): a step-number slot, node identity from the palette, and its config form — or a
// "read-only" note when the node has no knobs (encode/hydrate/deliver today).

import { findNodeCard, hasConfigFields } from "../../components/schema-form/paletteLookup";
import type { ActionBlob, Palette } from "../../api/types";
import { theme } from "../../theme";
import { NodeConfigForm } from "./NodeConfigForm";
import { SearchStageFrame } from "./SearchStageFrame";

interface SearchNodeCardProps {
  step: number;
  node: ActionBlob;
  palette: Palette;
  onChangeConfig: (field: string, value: unknown) => void;
}

export function SearchNodeCard({ step, node, palette, onChangeConfig }: SearchNodeCardProps) {
  const card = findNodeCard(palette, node.family, node.kind);
  const configurable = hasConfigFields(card);
  const number = (
    <span
      style={{
        width: 24, height: 24, borderRadius: "50%",
        background: theme.color.accentSoft, color: theme.color.accent,
        fontSize: theme.font.size.s, fontWeight: 700,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {step}
    </span>
  );
  return (
    <SearchStageFrame
      left={number}
      title={card?.name ?? node.kind}
      tag={node.family}
      summary={card?.summary}
      rightNote={configurable ? undefined : "read-only"}
    >
      {configurable && <NodeConfigForm node={node} palette={palette} onChange={onChangeConfig} />}
    </SearchStageFrame>
  );
}
