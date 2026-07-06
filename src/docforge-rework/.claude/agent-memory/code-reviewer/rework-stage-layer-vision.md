---
name: rework-stage-layer-vision
description: docforge-rework pipeline post-vision (2026-07-05) — what is the stage-layer substrate vs UI-dead vs advanced-only; the SchemaForm misplacement + double-wrap wart
metadata:
  type: project
---

# docforge-rework — stage-layer vision, what's live vs dead

Settled 2026-07-05: ingest pipeline = FIXED canonical stage order; users only toggle/pick-provider/edit-config/build-chains/order-stack via the STAGE API. Free-form graph wiring is NO LONGER a product feature — the graph engine is the internal EXECUTION SUBSTRATE only.

**Why:** center of gravity is now `shared/libs/pipelines/ingest/stages/` (spec→state→assembler↔reader→viewer→compiler). `IngestAssembler` is the SINGLE owner of wiring; `StageCompiler` = read blob→PipelineState→mutate→re-assemble (always buildable). The stage-rail UI (`app/frontend/src/features/stage-rail/`) is the default; `pipeline-editor/` (canvas studio, 36 files) is UNROUTED (kept for a hypothetical advanced mode per CollectionPipelinePage comment).

**How to apply — when reviewing rework pipeline changes:**
- Node-contract flags now UI-dead in the DEFAULT product (only the unrouted canvas / advanced mode reads them): `SWITCH_FIELDS` (only figure_classify declares it; stage layer routes off hardcoded `StageSpecs.FIGURE_BRANCHES`, not switch_fields), `describe().scored` (chains UI uses `ChainView`, not scored), the design-surface `recipes`/`mechanics`/`artefacts`/`run_inputs`/`explored`. Frontend refs to these exist ONLY in `api/types.ts`. They stay valid as substrate/advanced but flag any NEW work that leans on them for the default UI.
- `ERROR_POLICY` is read by the engine (`engine/core.py:412`) but NO node ever overrides `ErrorPolicy.FAIL`; enrich fail-soft is done with `OnFailure` edges, not the policy. Latent capability, not live.
- `UNIQUE_IN_GRAPH` validator rule (`validator.__check_unique_nodes`) is unreachable via the stage API (assembler emits each node once) — cheap defense-in-depth for hand/worker-loaded blobs; keep.
- **SchemaForm trio misplacement**: `SchemaForm→SchemaField→JsonField` live under `features/pipeline-editor/inspector/` but are imported by 3 stage-rail files (ChainStepCard, StackMethodCard, StageConfigForm). Deleting pipeline-editor WITHOUT extracting them first breaks the default UI. Trio is self-contained (only imports `api/types`, `theme`).
- **Double-wrap wart**: `StageViewResponse.stages: StageCatalog` and `StageCatalog.stages: list[StageView]` → JSON `{"stages":{"stages":[...]}}` (tests read `["stages"]["stages"]`).
- **edit/ module**: only `edit/topology.py` (`BlobTopology`) is a substrate dep (used by `StateReader`). `editor.py/operations.py/fragment.py/wiring.py/errors.py` serve ONLY the `/edit` endpoint (advanced). The stage compiler does NOT use `GraphEditor`.
- **Search-readiness / honest boundary**: `nodes/` (llm/ocr/vlm/embed/openai_compat) are genuinely generic (embed consumes shared `public_models.Chunk/CollectionContract`). The one boundary smell: `ingest/stages/models.py` (StageView/StageCatalog/StageAction/ChainStep/ChainView/StackMethod) is pipeline-AGNOSTIC but lives under `ingest/` — a future SearchPipeline importing it = cross-pipeline smell; lift to a shared `pipelines/stages_common/` before search.

Related: [[metagen-embed-node-traps]] (openai_compat factory), [[pipeline-engine-edge-selection]] (condition priority).
