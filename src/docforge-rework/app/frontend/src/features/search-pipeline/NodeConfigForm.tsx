// ====== Code Summary ======
// A search node's own config, resolved from the palette by (family, kind) and rendered with the
// shared SchemaForm — the search-pipeline analog of the stage rail's StageConfigForm, zero
// per-node frontend code.

import { SchemaForm } from "../../components/schema-form/SchemaForm";
import { findNodeCard } from "../../components/schema-form/paletteLookup";
import type { ActionBlob, Palette } from "../../api/types";

interface NodeConfigFormProps {
  node: ActionBlob;
  palette: Palette;
  onChange: (field: string, value: unknown) => void;
}

export function NodeConfigForm({ node, palette, onChange }: NodeConfigFormProps) {
  const card = findNodeCard(palette, node.family, node.kind);
  if (!card) return null;
  return <SchemaForm schema={card.config_schema} values={node.config} onChange={onChange} />;
}
