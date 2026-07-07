# RPI Research Brief — Dynamic self-describing stage architecture + backend-driven UI

> North star: `dynamic-stage-architecture-vision.md`. Design end-to-end before coding ("tout concevoir
> d'abord"). Three coupled features ride the same architecture: (1) metagen UX coherence, (2) a new
> chunk-filtering stage (parasitic/boilerplate removal), (3) doc + chunk activation.

---

## TL;DR — the shape of the target
Do for **stages** what is already done for **providers**: a self-registering catalog of self-describing
stage classes + a high-level assembler that builds the DAG dynamically + a generic engine that threads a
typed context and drives caching uniformly. The UI renders **100% from backend-emitted schema +
presentation metadata** — zero hardcoded text. The provider trio `@register`/`auto_import`/`build_union`
(`config/pipeline/_registry.py`) is the proven blueprint.

---

## PART 1 — CURRENT STATE & GAP ANALYSIS (codebase)

### 1A. Stages today = hand-wired, no interface
- **No `Stage` ABC/Protocol exists.** Each stage is an ad-hoc `LoggerClass` subclass with a **unique
  `run()` signature and unique constructor**; nothing self-declares name/description/order/IO/schema.
  - run() shapes (all different): S0 `(file_bytes,filename,doc_id)`; S1 `(s0,fingerprint)`; S2 `(s1,ir)`;
    S4 `(ir)`; S5 `(chunks,ir)`; S5b `(chunks,ir)`; S6 `(chunks,collection,session,metadata_fields,doc_meta)`.
  - Only partial self-declaration: `params_for_fingerprint()` on **2/7** stages (S2,S4); S0/S1 params
    extracted externally by `S012ParamHelpers` reaching into privates; S5/S5b/S6 declare nothing.
- **Assembly is hand-wired.** `ProviderRegistry.build_stages()` (`assembly/registry.py:82-112`) constructs
  each stage by name; `ResolvedStages` (`assembly/resolved.py:20-41`) is a **fixed dataclass**
  `parse_chain/s2/s4/s5/s5b`. `chain_builders.py` has **6 hardcoded `build_*` with `isinstance` switches**.
- **Order hardcoded in 3 places**: `StageEngine.run` (`orchestrator/core.py:147,222-264` literal calls +
  `stage_fingerprints={"s0","s1","s2"}`), the **fixed 7-tuple** `ResolvedStageTuple`
  (`stage_resolver.py:33-41`, unpacked in `core.py:194` + `worker_bootstrap.py:114`), and
  `_execute_s456` (`s456_runner.py:122-155`) with bespoke inter-stage threading + manual doc_meta merge.
- **Add-a-stage cost ≈ 9 edit sites** (confirmed from S5b): config sub-model; `PipelineConfig` field +
  `build_default_pipeline`; stage package; `chain_builders`; `registry` + `ResolvedStages`;
  `stage_resolver` tuple; `s456_runner` call; `core.py` threading; `worker_bootstrap` injection (+ the
  `stage_descriptors.py` literal + frontend stage def). **Target: collapse to ~1 (drop a class + register).**
- **Cache keying is per-stage copy-paste** (`s012_runner.py`): node versions are module constants, not on
  the stage; only S0/S1/S2 node-cached; S4/S5/S6 rely on PG/Qdrant idempotency. A uniform stage must
  declare `code_version`, `fingerprint_params()`, `input_keys`, `cache_policy`, and an artifact codec.
- **Layer DAG**: a `Stage` ABC + catalog belong in `common_libs/pipeline` (L3) — may import
  config/providers/storage/search/domain freely; the ABC must stay dependency-free of concrete stages
  (mirror `_registry.py`). The walking engine stays in `worker/libs/pipeline` (or moves to common if
  app+worker should share it).

### 1B. Two describe surfaces; stage identity not in the tree
- **Recursive `config_tree`** (`assembly/config_describer.py`, via `discovery/router.py:40,91-110`) is the
  target surface but carries **no stage identity** — stages are just Title-cased field names.
- **Flat `describe_stages()`** (`assembly/describe.py` + `stage_descriptors.py:40-144`) carries
  `id/label/name/description` **but as a hand-written dict literal**, not derived from classes; it also
  auto-imports the **dead `libs.providers.*` path** (silent ImportError swallow) — drift to delete.
- `ConfigNode` (`discovery/models.py:132-191`) already carries `path/kind/label/description/default/
  resolved/type/min/max/options/children/item_schema/choices`. Labels = schema `title` (auto field-name)
  or Title-case; descriptions = `Field(description=)`; the **only** ui hint honored is `{"ui":"text"}`
  (`config_describer.py:269`); secrets via `_is_secret_key`.
- **Provider self-description = the template to copy**: `@register("cat")` + `id: Literal[...]` (the key)
  + `_label` ClassVar (human name) + `Field(description=)` per field. Discovery reads exactly these.

### 1C. UI hardcoding inventory (~70-80 string sites across 9 files)
- **Stage identity 100% hardcoded TS**: `components/pipeline/stages.ts` (`INGESTION_STAGES`: label/icon/
  description/optional per s0..s6) + `search-stages.ts`. This is the biggest gap.
- **Config form ~90% backend-driven already**: `RecursiveFieldRenderer` dispatches by `kind`; reads
  label/description/type/options/min/max/default/capability/choices/item_schema from `ConfigNode`. Gaps:
  (a) TS `humanize()`+`ACRONYMS` fallback fires when a Pydantic field lacks `title`; (b) **object-node
  `description` is emitted but never rendered** as a section subtitle (1-line fix); (c) S5b cost-warning +
  MetagenPreview injected behind a hardcoded `if (stage.id==='s5b')` (`StageConfigPanel.tsx:304-320`).
- **S0 panel `IngestionConditionsPanel.tsx` is 100% handcoded** — it edits `ConfigState` top-level fields
  (`supported_formats`, `max_file_size_bytes`, `unknown_field_policy`, `metadata_fields`) NOT in the
  config_tree; hardcodes `FIELD_TYPES`/`UNKNOWN_FIELD_POLICIES`, all section titles, the metadata table.
- **Chain/gate copy 100% TS**: `ChainLadder`, `FailurePolicyControl`, `GateLimits`, `ProviderCard`.
- **Duplication**: `RenderChildrenFn` (×3), `paramsDefaults()` (×2), `humanize()` (×2) → extract to
  `ui/pickers/pickerHelpers.ts`.
- **Primitives are clean & reusable**: `ProviderUnionPicker`, `ObjectListPicker` (generic, `ui/pickers/`);
  `ChainLadder`, `ProviderCard`, `ChainGateDisplay`, `GateLimits`, `FailurePolicyControl` (domain,
  `pipeline/`). theme.ts disciplined; typed client + `gen:types`; rich `ui/primitives/` set.

### 1D. The metagen "type the field by hand" bug (root-caused)
`MetaGenTarget.field: str` → config_tree emits it as `kind=scalar,type=str` → `ObjectListPicker` renders a
**free text input**. The correct enum (collection's `origin="generated"` field names) IS built by
`overlays.py:_metagen_target_field()` but lands in `endpoint.dynamic_fields` (flat legacy), which the
config_tree render path **never consults**. Fix options: (A) backend patches the `object_list` `item_schema`
`field` node into `kind=enum` with overlay options; (B) frontend passes a path→override map from
`dynamic_fields` into `RecursiveFieldRenderer`. (A) is cleaner and aligns with the self-describing target.

---

## PART 2 — SOTA PATTERNS TO ADOPT (external)

### 2A. Self-describing pluggable stages
- **Haystack 2.x `@component`**: typed named input/output "sockets"; `@component.output_types(...)`;
  `Pipeline.connect("a.out","b.in")` with **validate-before-run** (existence/type/no-double-wire);
  `default_to_dict`/`from_dict` serialization. Closest match.
- **Dagster `Config` (Pydantic) → auto-rendered Launchpad**: the annotated Pydantic model IS the schema and
  drives a real editable, validated UI form with inline docs + "scaffold defaults". Proof the approach works.
- **Kedro connect-by-name**: nodes declare input/output **names**; the pipeline infers order by topological
  sort — lowest-ceremony DAG assembly.
- **LangChain Runnables**: auto-generated `input_schema`/`output_schema` from structure → contracts can't drift.
- **pluggy / `importlib.metadata.entry_points`**: spec=contract, manager=registry, ordering declarative
  (`tryfirst`/`trylast`) — the registry/assembler split.
- **Pydantic discriminated union** on a `Literal stage_type` tag → typed, round-trippable config + per-variant
  JSON Schema. **HF `PIPELINE_REGISTRY`**: one global registry both assembler and UI read.
- **8 adopted patterns**: stage self-declares (name/description/order-or-`after`/nested Config model/typed IO);
  one global registry; self-registration via entry_points/decorator+auto_import; connect-by-name +
  validate-before-run (= "collection = contract" fail-fast); discriminated-union config; round-trippable
  pipeline; auto-derived IO contracts; registry is the single source for assembler **and** UI.

### 2B. Backend-driven / schema-driven UI
- **JSON Schema can't express order/grouping/conditional visibility** → that's why a presentation layer
  exists. Two models: **RJSF** (one schema + sidecar `uiSchema`: `ui:widget/ui:order/ui:help/ui:options`,
  conditionals via `if/then/else`) vs **JSON Forms** (split data `schema` + layout `uischema` with
  `VerticalLayout/Group/Categorization`, `Control` bound by `scope` JSON-pointer, **first-class
  `rule:{effect:SHOW/HIDE, condition}`** for conditional visibility).
- **Pydantic v2 `model_json_schema()`** emits Draft 2020-12; **`Field(json_schema_extra={...})` is the
  injection point** for ui hints. Normalize before rendering: collapse `anyOf:[T,null]`, flatten
  `allOf:[{$ref}]`/root `$ref`; emit enums as **`oneOf:[{const,title}]`** (value+label) never bare `enum`.
- **Metadata the schema MUST carry**: title, description, help, widget, **explicit order**, **group/section**,
  conditional visibility, enums as value+label, defaults, constraints, **explicit secret flag**.
- **Secrets**: no lib does write-only round-trip — render masked, send a redaction sentinel, **skip on save
  if still equal to the sentinel** (DocForge already does this; keep it).
- **Recommendation**: keep ONE annotated JSON Schema (from Pydantic) as the data contract + a small
  backend-emitted **presentation descriptor** (order/groups/widget/secret/enum-labels/help) — JSON Forms
  philosophy sourced from Pydantic. Our `ConfigNode` tree is already 80% of this; extend it, don't replace.

### 2C. Parasitic/boilerplate chunk detection
- **Layout-label filter (FREE — Docling already runs)**: drop IR blocks whose label ∈ `{PAGE_HEADER,
  PAGE_FOOTER, DOCUMENT_INDEX}` (Docling `DocItemLabel` / `ContentLayer.FURNITURE`) or unstructured
  `{Header,Footer,PageNumber,PageBreak}`. **Match on `label`, not `content_layer`** (Docling #3015 nests
  furniture as BODY).
- **Cross-page recurrence (deterministic workhorse)**: blocks recurring in a top/bottom **position band**
  (~7% page height) across `≥ max(3, 0.5×page_count)` pages = furniture; normalize text (strip digits).
- **Page-number regex** (band-scoped): `^\s*\d{1,4}\s*$`, dashed, `page|p\.|pg\.\s*\d+(of|/)\d+`, Roman.
- **HTML furniture**: trafilatura blocklist (`nav/footer/aside/cookie/sidebar`) + jusText link-density
  (`>0.2`) + min-length, with trafilatura's **revert-if->85%-removed safety valve**.
- **Benchmark reality (SIGIR'23)**: heuristics are most robust; big neural models did poorly; ensembles win.
- **ML tier (defer, gate by DeviceManager)**: **DocLayNet-trained** detector (YOLO-DocLayNet → LayoutLMv3/DiT),
  NOT PubLayNet (only 5 classes, no header/footer). Run only on ambiguous/scanned/multi-column/`UncategorizedText`.
- **Design**: an ordered pipeline of pluggable **`FilterRule`** objects, each scoring a block furniture with
  confidence+reason, toggleable per-collection — i.e. the SAME stage-interface/chain pattern, applied to rules.

---

## PART 3 — TARGET ARCHITECTURE (to design in /rpi:plan)

### 3A. Stage interface + registry + assembler
- `Stage` Protocol/ABC in `common_libs/pipeline/stages/base.py` declaring: `name`, `description`, `order`
  (or `after: list[str]`), nested Pydantic `ConfigModel`, typed `consumes/produces` (context keys),
  `code_version`, `fingerprint_params()`, `cache_policy`, optional artifact codec. Uniform
  `run(ctx) -> ctx-delta` over a typed **PipelineContext** (replaces the divergent run() signatures).
- `@register_stage` + `auto_import` + a `STAGE_REGISTRY` (copy `_registry.py`); `PipelineConfig` becomes a
  **keyed map** `stages: dict[stage_name, StageConfig]` (discriminated union) so adding a stage needs no
  PipelineConfig edit. Assembler builds DAG by connect-by-name + topological sort + validate-before-run.
- Generic cache-aware engine loop replaces `StageEngine.run` + both runners + per-stage node-cache code.
- Generic chain builder dispatching on each stage-config field's declared provider category (retire the 6
  `isinstance` builders + `_FIELD_CATEGORY_MAP` → per-stage self-declaration).

### 3B. Self-describing config → backend-driven UI
- Add a `_stage` descriptor ClassVar (name/short_name/description/order/io_in/io_out/icon) on each stage
  config class; the describer reads it for stage object nodes → **retire `stage_descriptors.py` + the flat
  `describe_stages()` surface + the dead `libs.providers.*` import**.
- Extend the `ui` hook to a sub-dict: `Field(json_schema_extra={"ui":{"widget","group","order","help",
  "visible_if"}})`; widen `ConfigNode` with `group/order/help/widget/visible_if`; emit enum options as
  `{value,label,description}`; add provider/enum `_description`.
- Frontend: render object-node `description` (1-line); consume stage descriptors from discovery (kill
  `stages.ts` literals); generic `extra_components`/`ui_hints` dispatch (kill the `s5b` ID guard);
  consolidate `pickerHelpers.ts`; bring S0 (`IngestionConditionsPanel`) under discovery (add a
  `kind="metadata_schema"` node or source its labels/enums from discovery). Keep `RecursiveFieldRenderer`
  + pickers; only their hardcoded strings become backend-driven.
- Fix the metagen `field` dropdown (Part 1D, option A).

### 3C. Chunk-filter stage (new) — uses the same Stage + FilterRule pattern
- New stage between S4 (chunk) and metagen/embed. An ordered list of `FilterRule` (layout-label →
  cross-page-recurrence → page-number-regex → HTML-blocklist), each toggleable per-collection via the
  self-describing config; deterministic + free first; optional DocLayNet ML rule later, DeviceManager-gated.
- Output: marks chunks inactive (sets `chunk.active=False` with a reason) rather than deleting — feeds 3D.

### 3D. Doc + chunk activation
- **Postgres**: `document.active` (bool, default true, indexed) + `chunk.active` (raw-SQL repo: add to
  INSERT/SELECTs + `Chunk` dataclass). Toggle = plain `UPDATE`, never re-ingest.
- **Qdrant**: write `active` into the **S6 base payload** (`s6_embed_index/helpers.py:59-65`), NOT via the
  filterable loop. Toggle at runtime via the existing `set_points_payload` (payload-only patch, **no
  re-embed**). Reject delete/re-upsert (re-activation would need re-embedding = reindex).
- **Search**: inject `active=true` unconditionally via a `_require_active(filter)` mirroring `_pin_document`
  (`search/router.py:252`), feeding `Filter(**payload_filter)` (`qdrant/search.py:68`). A Search-Lab
  override may expose inactive deliberately.
- **Reindex-safe by construction**: `active` is row state, not `pipeline.*` and not a semantic/lexical field
  → `reindex_diff` returns `(False,[])` (same bucket as filterable-only metadata); `DocumentStaleness` too.
- **Metagen skips inactive**: filter `[c for c in chunks if c.active]` before the gather
  (`s5b_metagen/core.py:143`) + exclude from doc-scope digest → cost saved.
- **Caveat**: chunk id = UUID v5 of `(doc, block_ids, config_hash)`; chunk-level `active` survives re-ingest
  only if chunking config is unchanged. **Document-level activation (stable UUID) is the robust primary
  toggle; chunk-level is a config-stable refinement.**

---

## NEW FILES (indicative — finalized in /rpi:plan)
`common_libs/pipeline/stages/base.py` (Stage ABC/Protocol + PipelineContext); `common_libs/pipeline/
assembly/stage_registry.py` (`@register_stage`/`auto_import`/registry); chunk-filter stage package +
`FilterRule` base + rule impls; activation migration; frontend `pickerHelpers.ts` consolidation.

## MIGRATIONS
`document.active` + `chunk.active` (bool, default true, indexed). Possibly a `PipelineConfig` storage shape
change (flat fields → keyed `stages` map) — needs a config-blob migration/back-compat shim.

## NEW ENV VARS
Chunk-filter gate (mirror S2): `CHUNK_FILTER_ENABLED` default false (per-collection config still drives it,
per the metagen lesson — env gates the DEFAULT pipeline only).

## KEY CONSTRAINTS
IR canonical; provider URL+secret per collection; lean Qdrant payload; collection=contract fail-fast;
**config UI = backend-driven, zero hardcoded text**; layer DAG (domain←config←providers←storage←search←
pipeline) — Stage ABC at L3, dependency-free of concrete stages; double-cache/fingerprint must generalize;
env flag gates DEFAULT pipeline only (lesson from S5b: never gate explicit per-collection config).

## OPEN QUESTIONS (for /rpi:plan)
1. **Migration strategy & phasing**: this is a large refactor of a working pipeline. Big-bang vs strangler
   (introduce Stage ABC + registry alongside the current wiring, migrate stages one-by-one behind it)?
   Recommend strangler to keep the 780-test suite + live pipeline green throughout.
2. **`PipelineContext` design**: a typed object with declared keys vs Haystack-style named sockets vs Kedro
   connect-by-name. Affects how stages pass data and how the engine threads/caches.
3. **Ordering**: explicit `order` int (simple, but renumber pain the user dislikes) vs `after: [stage]`
   depends-on (topological, no fixed numbers — matches "numbering not hardcoded"). Recommend `after`.
4. **UI schema transport**: extend our `ConfigNode` tree (incremental, keep renderer) vs adopt JSON Forms
   schema+uischema wholesale. Recommend extend `ConfigNode` (80% there; lower risk).
5. **Chunk-filter placement vs S5b**: filter before metagen+embed (saves cost) — confirm it runs on IR
   blocks (pre-chunk) or on chunks (post-S4). The activation model wants chunk-level → likely post-S4.
6. **Scope of phase 1**: the user said "design everything" — but implementation should still phase. Propose:
   P1 stage-interface+registry+assembler (no behavior change) → P2 backend-driven UI + metagen fix → P3
   chunk-filter stage → P4 doc/chunk activation. Confirm the phasing in the plan's GO/NO-GO.
