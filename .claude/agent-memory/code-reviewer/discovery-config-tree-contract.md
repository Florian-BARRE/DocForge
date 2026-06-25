---
name: discovery-config-tree-contract
description: Frontend config_tree renderer — ConfigNode wire format, render-prop recursion, path-strip invariants, legacy fallback
metadata:
  type: project
---

The discovery `config_tree` (ConfigNode tree) drives the generic config UI, replacing the
old hardcoded per-stage panels. Key invariants when reviewing this area:

**Why:** the backend emits a recursive `ConfigNode` tree (kind = scalar/enum/object/
chain/provider_union) on config-bearing endpoints (create_collection, update_config). The
frontend renders it generically so adding a config field requires no frontend change.

**How to apply:**
- `RecursiveFieldRenderer.tsx` (components/ui) dispatches by `node.kind`. It breaks the
  apparent cycle renderer -> pickers -> renderer via a `renderChildren` RENDER-PROP, not
  lazy()/Suspense. ChainPicker + ProviderUnionPicker import nothing from the renderer.
- Path-strip invariant: backend roots update_config tree at `patch.pipeline`; StageConfigPanel
  maps `fieldPathPrefix` -> `patch.${prefix}` (treePathFor) and strips that prefix+'.' to get
  the key into its local `value` draft. All stage fieldPathPrefixes point at OBJECT nodes
  (parse/enrich/chunk/embed/search.{retrieve,rerank,query_transform}) — never directly at a
  chain/union — so `subtree.kind === 'object'` is the live branch; `[subtree]` is dead-safe.
- Pickers store provider params FLAT alongside `id` keyed by the LAST path segment
  ({id, ...params}). Safe because provider configs are one level deep (segments unique).
  Nested unions (semantic.embed) compose because each picker level scopes by its own value
  object; the outer picker's readParam/writeParam('embed') hand the nested object down.
- Legacy fallback is INTENTIONALLY kept: StageConfigPanel falls back to DynamicFieldsGroup
  (-> ChoicePicker -> SinglePicker/MultiPicker + pickerHelpers/NESTED_PROVIDER_FIELDS) when
  no config_tree is present. Those legacy files are NOT dead — do not flag them for deletion.
- Retired in D2 (deleted, must have zero imports): SearchStagePanel, TransformSection,
  RetrieveSection, RerankSection, EmbedSection, searchConfigHelpers.
- `resolveSelectedId` default = first available+selectable choice, NOT ProviderChoice.default
  (backend sets that flag inconsistently / always False).
- Backend Pydantic ConfigNode/ProviderChoice give `resolved`/`available` defaults (=True), so
  the common_libs describer omitting them is valid — validated at the router boundary.

Known cosmetic debt (not a blocker): mixed FR/EN UI strings (Annuler/Enregistrer/Historique)
pending a design-system pass.
