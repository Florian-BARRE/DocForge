// ====== Code Summary ======
// A stage's own top-level config (provider stages: the SELECTED kind's schema; toggle stages:
// the family's primary config-bearing node) rendered with the shared SchemaForm — zero per-stage
// frontend code.

import { SchemaForm } from "../../components/schema-form/SchemaForm";
import type { Palette, StageView } from "../../api/types";
import type { StageRailActions } from "./actions";
import { findNodeCard, primaryNodeCard } from "../../components/schema-form/paletteLookup";

interface StageConfigFormProps {
  stage: StageView;
  palette: Palette;
  actions: StageRailActions;
}

export function StageConfigForm({ stage, palette, actions }: StageConfigFormProps) {
  if (!stage.config || !stage.family) return null;
  const card = stage.kind === "provider"
    ? findNodeCard(palette, stage.family, stage.provider ?? "")
    : primaryNodeCard(palette, stage.family);
  if (!card) return null;
  return (
    <SchemaForm
      schema={card.config_schema}
      values={stage.config}
      onChange={(field, value) => actions.setConfig(stage.key, field, value)}
    />
  );
}
