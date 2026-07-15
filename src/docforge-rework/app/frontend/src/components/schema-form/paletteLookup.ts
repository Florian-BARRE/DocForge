// ====== Code Summary ======
// Small, generic lookups over the palette — the ONLY place any config-form-driven card (the
// ingestion stage rail, the search pipeline editor) resolves its node description. Nothing here
// names a specific family, stage or pipeline kind: a provider/chain/stack/node member is always
// matched by (family, kind), and the "primary" config-bearing node of a toggle stage is found
// generically (the family member whose schema actually declares fields), so a new backend family
// or a renamed node needs zero change here.

import type { FamilyCatalog, NodeCard, Palette } from "../../api/types";

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
 * Whether a chain family's providers carry a score a `score_below` escalation can read.
 *
 * Mirrors the engine's own rule (`Produces` subclassing `ScoredOutput` — parser/ocr/vlm are
 * scored, embed/llm/structgen are not) via the honest per-node `scored` flag the palette already
 * carries — no family name is special-cased here. A chain whose family reports unscored MUST NOT
 * offer a threshold input: the compiler silently drops any `score_below` on a non-scored chain
 * (failure-only fallback), so showing the field would be a lie.
 */
export function familyIsScored(palette: Palette, family: string): boolean {
  return findFamily(palette, family)?.nodes.some((n) => n.scored) ?? false;
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
