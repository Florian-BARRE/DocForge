---
name: stage-layer
description: The product-level stage view over the ingest graph (docforge-rework) — where it lives, its invariants, and the state-based compiler design
metadata:
  type: project
---

# Stage layer — the simple view over the ingest graph

The ingestion pipeline SHAPE is fixed. Users only: toggle stages on/off, pick THE provider for
exclusive stages, edit configs, build fallback CHAINS wherever a model (OCR/VLM/LLM) is called, and
order the contextualize stack. The stage layer publishes this as a vertical rail (no canvas).

**Why:** the graph editor is too low-level for collection owners; the stage layer is the
"ultra facile, aucun doute" face. The graph stays the runtime truth (worker/validator untouched).

**How to apply / where it lives:** `shared/libs/pipelines/ingest/stages/`
- `spec.py` — `StageSpecs.ORDER` = the 10 canonical stages (intake, parse, render, enrich, chunk,
  contextualize, metagen_chunk, metagen_document, embed, deliver) + `FIGURE_BRANCHES` (the enrich
  chain slots: scanned_text_ocr, photo_vlm, chart_vlm, diagram_vlm). Rename a stage HERE, all sides follow.
- `state.py::PipelineState` + `default_state()` — the canonical model BETWEEN blob and view.
- `assembler.py::IngestAssembler.assemble(state)` — the SINGLE owner of wiring (control-flow chain +
  the IR spine parse→render→enrich and chunks spine chunk→contextualize→metagen). `default_blob()` is
  now just `assemble(default_state())`.
- `reader.py::StateReader.read(blob)` — blob → state (family-first; derives chains by walking the loop body).
- `view.py::StageViewer` — state → `StageCatalog` (full skeleton, disabled stages `enabled=False`).
- `compiler.py::StageCompiler.apply(blob, action)` — parse→mutate state→REASSEMBLE. Always buildable.

**Key design decisions (durable):**
- Compiler = "parse blob → PipelineState → mutate → reassemble". Reassembly is what makes every
  toggle/rebind correct and always-buildable — never surgically edit the blob for stage actions.
- Dependency cascade: disable `render` cascades-disable `enrich`; enable `enrich` auto-enables
  `render`. Encoded via `StageMeta.requires`.
- Disable REMOVES the stage's nodes → its config is lost (blob is the only carrier). Re-enable
  restores stock build-safe DEFAULTS (from `default_state()`), NOT a prior edited config. This is
  intentional v1 — no side-channel persistence. Flagged in every disabled removable stage's `notes`.
- Missing required config (base_url/model) is a BUILD error, not a validation issue. So `set_provider`
  reset fills required str fields with `""` (empty str builds; validator doesn't check content).
- default_blob() was EXPANDED: the enrich loop now carries the full per-class chains (was just
  classify→entry). Top-level ids unchanged; body ids = classify, scanned_text_ocr_{0,1},
  scanned_text_ocr_entry, photo_vlm_0, chart_vlm_0, diagram_vlm_0, entry.
  AVOID reusing recipe-fragment ids (ocr_cheap/ocr_robust/describe) in the body — test_edit_api
  inserts the escalation_chain fragment onto the default and asserts those exact ids appear.

**Endpoints:** `POST /api/v1/pipelines/ingest/stages/view` and `.../stages/apply`
(+ `stages_view_url`/`stages_apply_url` on `PipelineSurface`). `CONTEXT.stage_compiler`.

**Proof:** scratchpad `test_stage_layer.py` (green alongside test_design_surface.py + test_edit_api.py).
