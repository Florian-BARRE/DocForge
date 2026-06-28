---
name: arch-recursive-gate-pairing
description: Generic multi-chain + gate pairing algorithm in RecursiveFieldRenderer — how chain nodes pair with their gate siblings and render as ChainLadder groups
metadata:
  type: project
---

## Generic chain+gate pairing in RecursiveFieldRenderer

`RecursiveFieldRenderer.tsx` implements a **GENERIC, path-suffix driven** algorithm that finds ALL
chain+gate sibling pairs at a given node level and renders each as a `ChainLadder` instance.

### Pairing rule (`gateSiblingSegFor` helper, line ~100)

```
chainSeg === "chain"        →  gate seg "gate"        (Parse, Embed)
chainSeg.endsWith("_chain") →  gate seg "X_gate"      (Enrich: classifier_chain→classifier_gate, etc.)
anything else               →  null (no pair)
```

### Algorithm (lines ~130–160)

1. Filter all `kind === "chain"` nodes from the sibling list.
2. For each chain, call `gateSiblingSegFor` and find the matching sibling `kind === "object"`.
3. Track consumed gates in a `Set<ConfigNode>` — they are excluded from `otherNodes`.
4. Render all pairs as `<ChainLadder>` instances (no per-stage hardcoding).
5. Render `otherNodes` with the standard scalar/enum/object/provider_union dispatch.

### Group title (`chainGroupTitle` helper)

Derives the section title from (in priority order): `node.capability` (e.g. "ocr" → "OCR") →
`node.label` strip trailing " Chain" → humanize path segment minus "_chain".

`groupTitle` is passed to `ChainLadder` only when `pairs.length > 1` (multi-chain stages like Enrich).

### ChainLadder `groupTitle` prop (ChainLadder.tsx)

When `groupTitle` is set, renders a `div.chain-group-title` above Section 1
("Providers — tried in order"). Section 1 keeps `borderTop: 'none'` regardless.
Adjacent `.chain-ladder + .chain-ladder` gets `margin-top: 20px` via CSS sibling combinator.

### Stage rendering verified (Playwright, 2026-06-28)

| Stage | Result |
|---|---|
| Enrich | 3 groups: Classifier / OCR / VLM (each with Providers/If-all-fail/Quality sections) + Chart To Data scalar toggle |
| Embed | Single chain+gate group (no title), PLUS Sparse provider_union with nested bge_server params |
| Parse | Single chain+gate group, clean 3 sections |
| Chunk | Scalars (Merge Short Sections, Reinject Breadcrumb) + Split Method provider_union (with nested Embed picker inside Semantic params) + Hierarchical scalar + ATOMIC object sub-section + Cross References scalar |

### Files touched

- `src/docforge/app/frontend/src/components/ui/RecursiveFieldRenderer.tsx` — multi-pair algorithm
- `src/docforge/app/frontend/src/components/pipeline/ChainLadder.tsx` — `groupTitle` prop
- `src/docforge/app/frontend/src/global.css` — `.chain-group-title`, `.chain-ladder + .chain-ladder`

**Why:** previous code used `nodes.find(n => n.kind === 'chain')` (only first chain) and matched gate
by `path.split('.').pop() === 'gate'` (missed `classifier_gate`, `ocr_gate`, `vlm_gate`).
