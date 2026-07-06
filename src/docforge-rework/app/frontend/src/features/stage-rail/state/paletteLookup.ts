// ====== Code Summary ======
// Small, generic lookups over the palette — the ONLY place a stage/chain/stack card resolves its
// node description. Nothing here names a specific family or stage: a provider/chain/stack member
// is always matched by (family, kind), and the "primary" config-bearing node of a toggle stage is
// found generically (the family member whose schema actually declares fields), so a new backend
// family or a renamed node needs zero change here.

import type { FamilyCatalog, NodeCard, Palette } from "../../../api/types";

export function findFamily(palette: Palette, family: string): FamilyCatalog | undefined {
  return palette.families.find((f) => f.family === family);
}

export function findNodeCard(palette: Palette, family: string, kind: string): NodeCard | undefined {
  return findFamily(palette, family)?.nodes.find((n) => n.kind === kind);
}

/** True when a node card actually has fields to edit (an empty `{}` schema needs no form). */
export function hasConfigFields(card: NodeCard | undefined): boolean {
  return Boolean(card && Object.keys(card.config_schema.properties ?? {}).length > 0);
}

/**
 * The node card that owns a TOGGLE stage's own top-level `config` (render/enrich/metagen_*).
 *
 * A toggle stage exposes exactly one editable config, but the family it draws from may list
 * several internal node kinds (e.g. enrich: classify/extract/entry/apply) — only the one that
 * actually makes a model call has a non-empty schema, so it's picked generically. Families whose
 * config-bearing members share an identical schema (metagen's chunk/document) resolve to the
 * first match — the values are the same shape either way.
 */
export function primaryNodeCard(palette: Palette, family: string): NodeCard | undefined {
  const nodes = findFamily(palette, family)?.nodes ?? [];
  return nodes.find((n) => hasConfigFields(n)) ?? nodes[0];
}
