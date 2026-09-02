// ====== Code Summary ======
// One step of the search rail, drawn in the shared SearchStageFrame (the ingestion StageCard's
// shape): a step-number slot, node identity from the palette, and its config form — or a
// "read-only" note when the node has no knobs (encode/hydrate/deliver today).

import type { ReactNode } from "react";
import { findNodeCard, hasConfigFields } from "../../components/schema-form/paletteLookup";
import type { ActionBlob, Palette } from "../../api/types";
import { NodeConfigForm } from "./NodeConfigForm";
import { SearchStageFrame } from "./SearchStageFrame";
import { StepNumberBadge } from "./StepNumberBadge";

interface SearchNodeCardProps {
  step: number;
  node: ActionBlob;
  palette: Palette;
  onChangeConfig: (field: string, value: unknown) => void;
  /** Extra content nested below this step's own config form — used to fold the query-transform
   *  toggle into the `normalize` step instead of giving it its own unnumbered sibling card. */
  extra?: ReactNode;
}

export function SearchNodeCard({ step, node, palette, onChangeConfig, extra }: SearchNodeCardProps) {
  const card = findNodeCard(palette, node.family, node.kind);
  const configurable = hasConfigFields(card);
  return (
    <SearchStageFrame
      left={<StepNumberBadge step={step} />}
      title={card?.name ?? node.kind}
      tag={node.family}
      summary={card?.summary}
      rightNote={configurable ? undefined : "read-only"}
    >
      {configurable && <NodeConfigForm node={node} palette={palette} onChange={onChangeConfig} />}
      {extra}
    </SearchStageFrame>
  );
}
