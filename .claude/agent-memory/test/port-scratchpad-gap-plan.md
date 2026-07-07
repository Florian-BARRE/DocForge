---
name: port-scratchpad-gap-plan
description: Verified 1:1 mapping of every scratchpad spec script to current shared_libs/worker/app source, plus the exact file list still to write for tests/units/nodes, tests/units/worker, tests/units/stages/test_view_reader.py, tests/units/api, tests/live. Read this BEFORE re-reading source — it was verified against the tree on 2026-07-02/03.
metadata:
  type: project
---

A prior session spent its whole budget verifying that every scratchpad script at
`.../795adf5a.../scratchpad/{test_providers,test_intake_stage,test_enrich_stage,test_enrich_failsoft,
test_chunk_stage,test_contextualize_stage,test_metagen_stage,test_embed_stage,test_worker_runner,
test_worker_translator,test_variant_pipeline,test_design_surface,test_edit_api,test_stage_layer}.py`
still matches current source **exactly** (no drift found anywhere checked) — but ran out of context
before writing any of the target pytest files. **Zero files were created; the gap in
[[stage-combinatorics-strategy]] and the MEMORY.md index is still fully open.** This memory is the
handoff so the next session can go straight to writing instead of re-reading.

## Confirmed-accurate API surface (safe to port verbatim, adapted to pytest style)

- **Providers**: `shared_libs.pipelines.nodes.ocr.base` (`BaseOcrNode`/`OcrConsumes`/`OcrProduces`/
  `BaseOcrConfig`), `.ocr.rapidocr.core/config` (real onnxruntime dep IS installed in `.venv`, via the
  `worker` dependency-group — `rapidocr_onnxruntime`, `pillow`, `pypdfium2` all present), `.vlm.base`
  (`BaseVlmNode`/`BaseVlmHelpers.extract_table`/`VlmConsumes`/`VlmProduces`/`BaseVlmConfig` — no
  `min_score` field, confirmed removed), `.vlm.openai_compatible.core/config`. All match the scratchpad
  1:1 including the `_TABLE_INSTRUCTION` fenced-block contract.
- **Intake stage**: `shared_libs.pipelines.ingest.nodes.intake.{admission,format_probe,pdf_probe,
  content_address,converter.gotenberg}` all match scratchpad exactly. `FormatProbeHelpers.detect`
  byte-signature rules confirmed line-for-line. `BaseConverterNode.run`: format=="pdf" passes through
  the original bytes untouched (`ConverterProduces(pdf=PdfView(content=data.source.content))`) — so the
  intake-stage E2E blob test needs **no HTTP mocking** for a PDF source, only for non-PDF formats.
  `AdmissionHelpers.validate_metadata`/`value_error` match every rejection case in the scratchpad
  (format/size/required/unknown/enum/type/generated-supplied/spoofed-extension/empty-file).
- **Enrich stage**: `figure_classify` (heuristics: `full_page_ratio`, `min_side_px`, `use_heuristics`,
  `SWITCH_FIELDS = {"kind": [...5 FigureKind values...]}`), `figure_extract` (`UNIQUE_IN_GRAPH=True`,
  skips blocks with no crop), `figure_entry`, `enrich_apply` (`UNIQUE_IN_GRAPH=True`, mutates the IR
  in place — the docstring explicitly warns callers not to reuse the pre-enrichment `ir` object after
  a run). All match scratchpad including the fail-soft `on_failure` routing pattern.
- **Chunk stage**: `chunk/base/{config,io,passages,node}.py` match scratchpad's `PassageProjector`
  behavior exactly (figure+caption fusion, table atomic, cyclic-parent-guard via `seen` set, header/
  footer excluded, `Passage.explode()` hard-cut semantics). `fixed_size`, `structure_aware`, `semantic`
  cores all match (structure_aware's `hard_section_boundaries`, semantic's context-window + percentile
  boundary detection). All 5 "audit fixes" (F1 cyclic parent, F2 oversized atomic stands alone, F4
  hard-cut run-on, F5 caption fusion) are still live behavior — safe to port as-is.
- **Contextualize stage**: `base/{node,io,config}.py`, `breadcrumb`, `doc_meta` (+ `DocMetaConsumes`
  extends the family face with `source`), `sliding`, `llm/{core,config}.py` (`DocumentScope` FULL/
  SECTION/WINDOW, `OnChunkError` KEEP_RAW/FAIL, `_situate(document, chunk_text)` hook signature,
  batch override precomputes the FULL view once). All match scratchpad including the F1/F2 audit fixes
  (full view built once, structure preserved under the word cap).
- **Metagen stage**: `base/{config,node,helpers}.py` — `MetagenTarget`, `MetagenGrouping` (COMBINED/
  PER_FIELD), `_resolve_targets` (raises on duplicate/unknown/wrong-scope target field, `"more than
  once"` / `"not a GENERATED field"` messages), `_generate_values` (groups by endpoint, strict
  coercion via `MetagenHelpers.coerce`), `chunk/core.py` (MERGES `generated_meta`, never clobbers —
  confirmed at line ~91 `{**chunk.generated_meta, **values}`), `document/core.py`. `MetagenHelpers.
  coerce` handles all 11 `FieldType` values (STRING/INTEGER/FLOAT/BOOL/KEYWORD_LIST/DATETIME/ENUM/
  TEXT/INTEGER_LIST/FLOAT_LIST/TEXT_LIST) — `_TYPE_SCHEMAS` dict in helpers.py is the enumeration to
  parametrize a coercion test over. Enum whitelist injection: `fragment["enum"] = [*spec.enum_values,
  None]` in `object_schema` — test by asserting the schema, not by mocking a model response.
- **Embed stage**: `base/{config,node,io}.py` match scratchpad (`embed_sparse`, `embed_semantic_fields`
  flags; sparse axis dropped gracefully when `_embed_sparse` returns None — logged once). `bge_server/
  core.py` posts to `/embed` and `/embed_sparse` via `httpx.AsyncClient` (mock via `httpx.AsyncClient.
  post` monkeypatch or `respx`, or just subclass `BaseEmbedderNode` with fake `_embed_dense`/
  `_embed_sparse` hooks like the scratchpad does — simpler, no HTTP mocking needed for the base-class
  contract tests). Record-strip confirmed in `shared_libs/pipelines/engine/core.py` lines ~87-111:
  `FlowEngine._NUMERIC_LIST_LIMIT = 64`, `__strip_payloads` turns any numeric list > 64 items into
  `f"<{len(value)} numbers>"` and bytes into `f"<{len(value)} bytes>"`, recursively over dict/list.

## Worker (tests/units/worker/ — HIGHEST PRIORITY per coordinator)

- `worker/backend/libs/runner/core.py`: `PipelineRunner.run(blob, source, contract, timeout_seconds,
  progress_callback=None) -> tuple[RunBundle, NodeExecutionRecord]`. Raises `PipelineRunError` with
  `"invalid pipeline graph"` (bad graph), `"pipeline run failed: {reason}"` (engine failure), or
  `"...must end on a deliver/bundle node producing a RunBundle"` (output contract) — all 3 match
  scratchpad's assertions on the exception string.
- `worker/backend/libs/persistence/translator.py`: `RunTranslator.translate(document_id, bundle,
  schema, strategy, config_hash) -> TranslatedRun` (dataclass: `payload, objects, blob_rows, points,
  dense_dim`). `__block_id` remap = `f"{document_id}:{pipeline_id}"`. `__register_blob` **dedup lives
  here**: `if all(row.content_hash != content_hash for row in out.blob_rows): append`else skip — so a
  DEDUP test needs two artefacts with IDENTICAL bytes (e.g. two `PageRender`s with the same `image=
  b"..."`) and must assert `len(out.blob_rows) == 1` and `len(out.objects) == 1` while
  `len(out.payload.pages) == 2` (both rows reference the same `render_blob_hash`). Chunk UUIDs minted
  in `chunk_uuids: dict[str, uuid.UUID]` — one per pipeline `chunk_id`, reused for `ChunkBlock`,
  `ChunkMetadata`, and the Qdrant point id. `VectorNames` (`shared_libs.services.db.qdrant.vectors.
  names`): `CONTENT_DENSE="content_dense"`, `CONTENT_SPARSE="content_bm25"`, `field_dense(name)=
  f"meta_{slug}_dense"`. `QdrantPoint`/`SparseVec` are plain `@dataclass(slots=True)` in `...qdrant.
  vectors.point`. ORM table classes (`Blob, BlockFigure, Chunk, MetadataField, Page, ...` from
  `shared_libs.services.db.postgresql.tables`) are plain SQLAlchemy declarative classes — constructing
  them with kwargs in a test does NOT touch a real DB (no session involved), exactly like the
  scratchpad does.
- `deliver/bundle/core.py`: `BundleNode` (`UNIQUE_IN_GRAPH=True`) assembles `RunBundle(ingest, ir,
  pages, chunks, document_meta, embeddings)` — `pages`/`document_meta`/`embeddings` all
  `Optional[...] = None` (the variant-pipeline "optional slots" test target). `FlowEngine.execute`
  returns the TERMINAL node's `Produces` instance as `output` — so `output.bundle` works because the
  last node in the graph is the `bundle` node whose `Produces.bundle: RunBundle`.
- Root `tests/conftest.py` already adds `worker/backend/libs` to `sys.path` (NOT the `worker/` root —
  confirmed by grep that `runner/core.py` and `persistence/translator.py` only ever import
  `shared_libs.*`, never a worker-local `config`/`backend` package) — so `tests/units/worker/*.py` can
  do `from runner import PipelineRunner, PipelineRunError` and `from persistence import RunTranslator`
  directly, with ZERO extra path bootstrap needed in a local conftest (unlike the standalone scratchpad
  scripts, which added `worker/` root too — do NOT replicate that in pytest, it would collide with the
  app's own top-level `backend`/`config` packages the way [[bootstrap-mechanics]] warns about).

## Confirmed STILL-OPEN test gaps in tests/units/stages/ (not just the node-family port)

Cross-checked `test_stage_layer.py`'s 9 sections against existing `tests/units/stages/*.py`:
sections 1 (`default_blob` canonical top-level id list + 0 issues) and 2 (`StageViewer.catalog` full
10-stage-key run order with all enabled + `removable`/`available` flags) are NOT covered by any
existing test. Sections 4a/4b (**disable enrich alone → chunk.ir rebinds to render's `figures.ir`,
0 issues, no "render" notice**; **disable render CASCADES enrich off (with a notice) → chunk.ir falls
back to `parse.ir`, `bundle.pages` unbound**) are the compiler-cascade-correctness test explicitly
flagged as missing in [[stage-combinatorics-strategy]] — grepped the whole `tests/units/stages/` tree
on 2026-07-05 and confirmed no test exercises `DisableStage(stage="enrich")` or
`DisableStage(stage="render")` today. This belongs in a new `tests/units/stages/test_view_reader.py`
per the task brief (which also wants: default_blob canonical ids + 0 issues; disable/enable cascades
+ notices — i.e. exactly scratchpad sections 1-4b). Sections 5-8 (set_provider/set_chain/set_stack/
round-trip) ARE already covered by `test_providers.py`/`test_chains.py`/`test_stack.py` — skip
re-porting those. Section 9 (the `/stages/view` + `/stages/apply` endpoints) belongs in
`tests/units/api/test_stage_endpoints.py` instead.

## API layer (tests/units/api/ — confirmed against current router source)

- `app/backend/routers/pipelines/router.py` + `models.py`: `GET /api/v1/pipelines` (index),
  `GET /api/v1/pipelines/ingest?full=` (lean vs full palette — `palette.run_inputs/mechanics/
  artefacts` are `None` unless `full=true`), `POST .../inspect`, `POST .../edit` (impossible op →
  200 + `edit_error` set + ORIGINAL blob echoed, never a 500), `POST .../stages/view` (validity folded
  into the same response, `build_error` set instead of raising on an unbuildable blob), `POST .../
  stages/apply` (same build-error-as-data contract; a `SetChain` step missing a required config field
  gets auto-filled `""` by the compiler, so apply always builds even before the user fills secrets —
  matches `test_chains.py::test_chain_step_config_is_completed_build_safe`, port an API-level
  equivalent). All response models confirmed in `models.py` (`PipelineDesignResponse`,
  `InspectResponse`, `EditResponse`, `StageViewResponse`, `StageApplyResponse`).
- `test_edit_api.py` scratchpad sections 1-5 (GraphEditor direct calls: add_node auto-wire,
  remove_node bridge+purge, insert_fragment suffixing, set_binding, EditError messages) are ALREADY
  fully covered by `tests/units/edit/*.py` (confirmed by file names: test_add_node_and_loop,
  test_edit_errors, test_insert_fragment, test_remove_node, test_set_operations) — only section 6 (the
  actual `POST /edit` HTTP round trip: happy path + impossible-op-echoes-original-blob) is the real gap
  for `tests/units/api/test_edit_endpoint.py`.
- `test_design_surface.py` scratchpad (zero mute Field descriptions across EVERY registered node's
  Config/Consumes/Produces; `scored`/`switch_fields` auto-derivation; `FamilyMode` per family in the
  palette; lean-vs-full `IngestPipeline.palette()`) is entirely unported — belongs in
  `tests/units/api/test_design_surface.py` (can hit it either via direct `IngestPipeline`/
  `NodeRegistry` calls, no TestClient needed except to confirm the `?full=true` query flows through
  the router, OR go through `client.get("/api/v1/pipelines/ingest")` for the endpoint-level slice).

## Next-session execution order (unchanged from the coordinator's priority)

1. `tests/units/worker/` — `test_worker_runner.py` (RunBundle contract, 5 behaviors), `test_worker_
   translator.py` (5 axes incl. the dedup test above), `test_variant_pipeline.py` (optional slots).
2. `tests/units/nodes/` — one file per node family, ported per the "confirmed-accurate" section above.
3. `tests/units/stages/test_view_reader.py` — default_blob ids/view + the disable-cascade pair.
4. `tests/units/api/` — test_design_surface, test_edit_endpoint, test_stage_endpoints,
   test_collections_validation (this last one was NOT yet researched this session — read
   `app/backend/routers/collections/{router,models}.py` fresh before writing it).
5. `tests/live/` — NOT yet researched this session either; read `tests/live/conftest.py` +
   `app/backend/routers/{collections,documents,jobs}/router.py` fresh, and the collections router's
   field-type validation paths (11 field types, enum-without-whitelist, semantic integer_list 422,
   PATCH rename/409/needs_reindex) before writing.

See also [[bootstrap-mechanics]], [[noderegistry-global-state]], [[stage-combinatorics-strategy]].
