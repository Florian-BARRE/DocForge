---
name: code-reviewer-memory
description: DocForge-specific code review checklist, anti-patterns, and past findings
metadata:
  type: project
---

# Code Reviewer Memory

## Non-negotiable rules (from feedback)

- **Docker + docker compose (v2)** — `docker build`, `docker compose up`; never `podman` or legacy `docker-compose`
- **SeaweedFS only** — never write MinIO anywhere
- **loggerplusplus only** — no `print()`, no direct loguru import
- **LoggerClass.__init__(self) required** — every subclass must call it explicitly
- **RUNTIME_CONFIG first** — always the first internal import in entry points
- **English only** — all code, comments, docstrings, variable names

## Review checklist — Python (python.md)

- [ ] Every instanciable class: inherits `LoggerClass`, calls `LoggerClass.__init__(self)`
- [ ] No `print()` or `import loguru` anywhere in application code
- [ ] All log messages are f-strings: `self.logger.info(f"Done")` not `self.logger.info("Done")`
- [ ] Import order: stdlib → third-party → `from config import ...` → relative imports
- [ ] File header: `# ====== Code Summary ======` (except `__init__.py`)
- [ ] `__init__.py`: labeled sections + `__all__`
- [ ] Static helpers class: `__new__` raises `TypeError`, logger bound at class level

## Review checklist — FastAPI (fastapi.md)

- [ ] `@auto_handle_errors` on every route (between `@router.verb` and `async def`)
- [ ] `response_model` declared on every route
- [ ] No business logic in `router.py` — only calls to `CONTEXT.service.method()`
- [ ] `CONTEXT.attr` used for all services — never import instances directly in routers
- [ ] `hasattr(CONTEXT, "attr")` guards in `lifespan.py` `finally` block

## Review checklist — DocForge invariants

- [ ] IR is canonical — no code writes raw markdown/PDF as source of truth
- [ ] Every provider implements its `Protocol` — duck-typed, no concrete coupling
- [ ] No device logic (CUDA/CPU) inside individual providers — only in `DeviceManager`
- [ ] New env vars: shared → `BaseRuntimeConfig` (`common/base_config/runtime/base_config.py`); app/worker-only → the per-app `RUNTIME_CONFIG(BaseRuntimeConfig)` subclass; plus `services/docforge/.env`
- [ ] Schema change: Alembic migration present in `common/migrations/versions/`
- [ ] New pipeline stage: wired as DAG node in `worker/libs/pipeline/engine.py`
- [ ] New stage: idempotency guaranteed (Postgres ON CONFLICT DO NOTHING, Qdrant upsert)

## Topic memory files (read on demand)

- [layer_dag](layer_dag.md) — libs layer DAG import rules to enforce, esp. storage vs search
- [reindex_staleness_coherence](reindex_staleness_coherence.md) — reindex_diff shared between config bump + per-doc staleness; fragile transient `_reindex_reasons`
- [secret_roundtrip](secret_roundtrip.md) — `ConfigDocument.merge_patch` preserves redacted secrets — validated, do NOT flag
- [page_indexing_zero_based](page_indexing_zero_based.md) — page numbers are 0-indexed end to end; page-1-as-first is off-by-one
- [search_pipeline_antipatterns](search_pipeline_antipatterns.md) — P7 search pipeline (engine, rerank, fusion) recurring issues
- [observability-brick-a](observability-brick-a.md) — Brique A audit anti-patterns (queue/metrics/heartbeat/events + jobs/monitoring routers)

> Component-scoped memory lives with the component agents: **`mcp`** agent (`agent-memory/mcp/`) for
> the `src/mcp/` HTTP-client invariant + REST endpoint map; **`bge-server`** agent
> (`agent-memory/bge-server/`) for the `src/bge_server/` model host. Consult them when reviewing
> those trees; this file holds the cross-cutting product rules.

## Common anti-patterns seen in this codebase

- Passing `collection_id` as a positional arg instead of keyword — causes silent None
- Forgetting `await` on async repo methods — Python won't warn, returns coroutine object
- Hardcoding `http://localhost:8000` instead of using `RUNTIME_CONFIG.DOCFORGE_API_URL`
- Using `os.environ.get()` in application code — must use `RUNTIME_CONFIG` instead
- Returning raw `dict` from a route instead of a Pydantic model
- Accessing `.params` on a typed Pydantic provider config (DoclingConfig, TeiEmbedConfig, …) —
  post the flat-config refactor these have **flat top-level fields**, no `.params`. Use
  `cfg.model_dump(exclude={"id"})` to get the params dict, or `getattr(cfg, "base_url", "")`
  for a single attribute. The legacy `ProviderSpec(id, params)` is kept only for back-compat
  in DB loading.
- Validator capability strings drifting from `ProviderRegistry.describe_stages()` ids
  (seen: `chunk_strategy` vs `split_method`). Verify both sides agree before adding a
  `_check_one("<cap>", …)` call — a mismatch makes every collection create raise
  `Unknown <cap> provider 'token_budget'`.
- Returning a SQLAlchemy model from a `repo.create()` without refreshing relations needed
  outside the session — triggers `DetachedInstanceError` on lazy load. Use
  `await session.refresh(collection, attribute_names=[...])` before returning.
- Registry params using `"key"` instead of `"name"` (ParamSchema's required field).
  Caused `/api/v1/discovery` to 500 silently — the UI then showed an empty form for
  every endpoint. Always serialize provider/stage params with `{"name": ..., "type": ...}`,
  never `{"key": ..., "note": ...}`. The discovery overlay validates via
  `ParamSchema.model_validate()` and will fail loudly on drift.
- Adding a pipeline param (chart_to_data, hierarchical, …) without emitting a
  DynamicField overlay — the UI cannot surface it. `discovery/overlays.py`'s
  `_pipeline_dynamic_fields` now emits `kind="scalar"` for every stage-level param;
  the matching frontend branch is `ScalarPicker` in `ChoicePicker.tsx`. Both sides
  must agree on the kind enum (DynamicFieldKind in `types.ts`).

## Frontend architecture invariants

- Forms are NEVER hand-coded per endpoint. The primitives are
  `<RequestForm endpoint=… discovery=…>` (static body + query + root overlays) and
  `<DynamicFieldsGroup fields=… prefix=…>` (nested overlays grouped by sub-path,
  e.g. `pipeline` for create, `patch.pipeline` for update_config). Five canonical
  consumers: CollectionStep, ConfigStep, IngestStep, SearchView, BrowseView —
  if a new view fetches an endpoint with a body or query, it MUST go through
  RequestForm so adding a backend Pydantic field surfaces automatically.
- Any addition to a Pydantic request model is a UI feature: there is no separate
  UI ticket. Verify the new field appears by reloading /discovery in the browser.

## Chain framework invariants (Phase A — generalised provider chains)

- Every ML stage uses `common_libs.providers.chain.Chain[T, R]` — parse, classifier, OCR,
  VLM, embed. New providers plug in by exposing `score() -> float | None` on
  their result type (see `common_libs/providers/scoring.py::ScoredResult`).
- Pipeline config fields are ALWAYS `chain: list[…]` + `gate: ChainGateConfig`
  (or `<stage>_chain` + `<stage>_gate` inside `EnrichConfig`). A legacy
  `{provider: {...}}` blob is lifted via `_lift_provider_to_chain` so old
  DB rows still load. Adding `provider:` instead of `chain:` is a regression.
- Chain attempt traces are persisted on the IR:
  - `DocumentIR.chain_traces` for stage-level chains (parse, embed).
  - `Block.chain_traces` for block-scoped chains (classifier, OCR, VLM per figure).
  - `DocumentIR.quality_score` carries the parser's intrinsic quality estimate
    consumed by the parse chain gate.
- Discovery emits `kind="multi"` for every chain field path and
  `kind="scalar"` for every `<stage>.gate.min_score` (and stage-level scalar
  params). The UI's existing `MultiPicker` + `ScalarPicker` render them for
  free — no per-stage frontend code.
- Logging format is canonical: `[CHAIN <stage>] attempt N/M provider=X
  score=… duration_ms=… → escalate|final`. Any chain user MUST go through
  `Chain.call()`; bypassing it skips traces, logs, and the gate.
- Stage classes accept their chain instance, never a single provider:
  `S1ParseStage(parse_chain=…)`, `S2EnrichStage(classifier_chain=…,
  ocr_chain=…, vlm_chain=…)`, `S6EmbedIndexStage(embed_chain=…)`. The
  registry's `_build_<stage>_chain` helpers are the single construction
  point — entrypoint/worker MUST go through them, not instantiate
  providers directly.
