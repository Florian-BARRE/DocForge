---
name: chain-gate-config-paths
description: How the pipeline provider chain + gate UI serialize into the config patch — use to verify chain/gate edits write to correct config_tree paths
metadata:
  type: project
---

The pipeline config UI (Pipeline tab) edits provider chains + gates through a
config_tree-driven path. Verified correct as of 2026-06-26 redesign.

**Wire format (must not regress — backend depends on it):**
- A chain value is an ordered array of entries `{ id, ...flatParams }` — provider
  params are stored FLAT on the entry keyed by the param's LAST path segment.
- The gate is a SIBLING object of the chain; its fields (`min_score`,
  `max_duration_ms`, `failure_policy`, `on_degraded`) write to `gate.<field>`.

**Path plumbing (StageConfigPanel → RecursiveFieldRenderer → ChainLadder):**
- `treePath = patch.<fieldPathPrefix>` (e.g. `patch.pipeline.embed`); the backend
  roots the `update_config` config_tree at `patch.pipeline`.
- chain ConfigNode path = `patch.pipeline.<stage>.chain`; gate path =
  `patch.pipeline.<stage>.gate`.
- `readValue`/`writeValue` strip `treePath + '.'` to get the key relative to the
  stage-rooted draft `value` object, then use `readPath`/`setPath` (pathUtils.ts).
- `handleChange` rebuilds the nested patch from `fieldPathPrefix` via reduceRight,
  staged into `useConfigDraft` → saved by `ConfigSaveBar`.

**How to apply:** When reviewing chain/gate UI changes, confirm: (1) chain writes
to `<chainNode.path>` (ends in `.chain`), (2) gate fields resolve via
`path.endsWith('.<field>')` and write through the SAME readValue/writeValue
accessors (so they land under `gate.*`), (3) provider params use last-segment flat
keys. A wrong path here SILENTLY breaks saves (no error, just lost edits) — it is
the highest-risk regression in this area. ChainLadder replaced the old
`components/ui/pickers/ChainPicker.tsx` (now orphaned/dead) with identical wire
format; old `PipelineGraph`/`StageNode` still serve SearchTab (intentional).
