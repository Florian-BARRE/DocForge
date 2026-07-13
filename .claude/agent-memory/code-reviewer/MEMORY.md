---
name: code-reviewer-memory
description: DocForge-specific code review checklist, anti-patterns, and past findings
metadata:
  type: project
---

# Code Reviewer Memory

Reviews target the ACTIVE product `src/docforge-rework/` (being renamed `docforge`). `src/docforge/` is
FROZEN legacy — don't review it unless explicitly asked.

## Non-negotiable rules (from feedback)

- **Docker + docker compose (v2)** — never `podman` or legacy `docker-compose`
- **SeaweedFS only** — never write MinIO anywhere
- **loggerplusplus only** — no `print()`, no direct loguru import
- **LoggerClass.__init__(self) required** — every instanciable subclass must call it explicitly
- **RUNTIME_CONFIG first** — always the first internal import in entry points
- **English only** — all code, comments, docstrings, variable names

## Review checklist — Python (python.md)

- [ ] Every instanciable class: inherits `LoggerClass`, calls `LoggerClass.__init__(self)`
- [ ] No `print()` or `import loguru` anywhere in application code
- [ ] All log messages are f-strings
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

## Review checklist — DocForge invariants (rework tree)

- [ ] IR is canonical — no code writes raw markdown/PDF as source of truth
- [ ] **Node purity** — a pipeline node does Consume→Produce with ZERO DB/S3/Qdrant I/O; persistence
      happens at the edges in the worker via the `shared_libs.services.db` `Database` façade
- [ ] Every slot AND every config field carries a `description` (a test rejects undescribed ones)
- [ ] Device (CUDA/CPU) is a deployment env decision — never a per-collection provider config field
- [ ] A broken pipeline blob returns as DATA (`valid=false` + issues) via `GraphValidator`, never HTTP
- [ ] New env var: shared → the common base config; app-only → `app/config/runtime_config.py`;
      worker-only → `worker/config/runtime_config.py` (+ the matching `services/*/.env`)
- [ ] Schema change: Alembic migration present in `src/docforge-rework/shared/migrations/versions/`
- [ ] New node: registered in a family under `shared/libs/pipelines/` (`nodes/<family>/` for generic
      providers, `ingest/nodes/<stage>/` for stage nodes); declares family/kind + typed described slots
      via `describe()`; `UNIQUE_IN_GRAPH` set correctly
- [ ] Idempotency at persistence edges (Postgres upsert; Qdrant upsert) — see [[db-layer-review-heuristics]]

## Topic memory files (read on demand)

### Engine, nodes & IR
- [describe-reflection-fragility](describe-reflection-fragility.md) — `describe()` reads `annotation.__name__` and crashes on union/optional slots; one bad slot breaks the whole palette.
- [foreach-primitive-traps](foreach-primitive-traps.md) — ForEach/WhenEquals/SlotTypes traps: non-Artifact item_type crash, ValidationError escaping per-node try, no ge=1 guard, progress/trace duplication.
- [foreach-chain-terminal-item-type](foreach-chain-terminal-item-type.md) — chain+OnFailure→skip ForEach body: item_type() sees only the static skip exit; safe iff every step+terminal produces the SAME single-slot artefact (runtime re-check fails loud, never silent).
- [pipeline-engine-edge-selection](pipeline-engine-edge-selection.md) — FlowEngine ranks edges by specificity (ScoreBelow>WhenEquals>OnSuccess/OnFailure>Always); cross-rank fixed, SAME-rank fan-out still order-dependent.
- [foreach-sibling-duplicate-ids-safe](foreach-sibling-duplicate-ids-safe.md) — sibling ForEach bodies may reuse the same group/node ids; ids are per-scope. Nothing (engine lookup, trace tree, progress roots, persistence, no cache) assumes global uniqueness — not a finding by itself.
- [fingerprint_stage_flag_gap](fingerprint_stage_flag_gap.md) — node-cache: a stage-level flag (not a chain field) dropped from the Merkle fingerprint → stale cached output.
- [enrich-trace-and-failure-traps](enrich-trace-and-failure-traps.md) — enrich: byte-carrying artefacts bloat the execution trace ~8x, `enrich_apply` mutates run_input in place, one flaky figure fails the doc.
- [contextualize-llm-perchunk-traps](contextualize-llm-perchunk-traps.md) — per-chunk-LLM node traps (the shape metagen copies): O(n²) doc-view rebuild, whitespace flattening, over-broad keep_raw try.
- [metagen-embed-node-traps](metagen-embed-node-traps.md) — metagen + embed node traps: chunk-metagen overwrites generated_meta on chaining, duplicate targets dedupe, datetime hint dropped; openai_compat factory consumer count.
- [model-cache-concurrency](model-cache-concurrency.md) — ModelCache per-lib inference-locking: which heavy providers MUST serialize inference and which must not.
- [locality_empty_chain_nameerror](locality_empty_chain_nameerror.md) — latent NameError: code after a for-loop using the loop var crashes on an empty iterable.
- [coalesce-fragment-run-guard](coalesce-fragment-run-guard.md) — greedy coalesce-small passes guarding only the incoming size let a sub-target REAL unit absorb fragments; needs a fragment-run origin flag.
- [rework-stage-layer-vision](rework-stage-layer-vision.md) — post-vision map (2026-07-05): stage-layer substrate vs UI-dead vs advanced-only; the SchemaForm misplacement + double-wrap wart.
- [layer_dag](layer_dag.md) — libs layer DAG import rules to enforce, esp. storage vs search.
- [public_models_pipelines_import_cycle](public_models_pipelines_import_cycle.md) — P5a made public_models ↔ pipelines.base a bidirectional cycle resolved only by __init__ line ordering; layering inversion to watch.
- [page_indexing_zero_based](page_indexing_zero_based.md) — page numbers are 0-indexed end to end; page-1-as-first is off-by-one.
- [bbox_normalized_overlay](bbox_normalized_overlay.md) — IR bbox is normalized [0,1]; overlay code that scales by page points/zoom collapses boxes to the corner.

### Data layer, config & search
- [db-layer-review-heuristics](db-layer-review-heuristics.md) — rework FK-only store pitfalls: self-FK insert batching, unindexed FKs, enum value binding, Qdrant filter/slug gaps.
- [reindex_staleness_coherence](reindex_staleness_coherence.md) — reindex_diff shared between config version-bump + per-doc staleness; the fragile transient `_reindex_reasons`.
- [secret_roundtrip](secret_roundtrip.md) — `ConfigDocument.merge_patch` preserves redacted secrets — validated correct, do NOT flag.
- [search_pipeline_antipatterns](search_pipeline_antipatterns.md) — recurring correctness/coherence issues in the search pipeline (engine, rerank, fusion).
- [rework_search_endpoint](rework_search_endpoint.md) — rework hybrid-search read path: named-vector-via-constants, openai dense-only degrade, secret handling, and the never-ingested→500 facade gap.
- [multivector-upsert-byte-limit](multivector-upsert-byte-limit.md) — ColBERT/multivector upserts must batch by ESTIMATED BYTES: a full-precision colbert batch crosses Qdrant's 32 MB max_request_size → instant 400 + connection reset masquerading as httpx.ReadError; intermittent by token count.

### Auth & scoping
- [auth_keys_only_capabilities](auth_keys_only_capabilities.md) — AUTH keys-only model: capability taxonomy + require_capability; null=full-access footgun; what NOT to flag.
- [collection_scope_idor](collection_scope_idor.md) — every `{collection_id}/{document_id}` route MUST check `doc.collection_id == collection_id` or it's a cross-collection IDOR.
- [stale-scoped-tab-bypasses-gate](stale-scoped-tab-bypasses-gate.md) — per-collection sub-tab state survives a collection switch and bypasses a gate that only HIDES the tab.

### Frontend & SSE
- [antipattern-static-dom-ids](antipattern-static-dom-ids.md) — hardcoded HTML id/htmlFor break when a component renders more than once on the same screen.
- [frontend-sse-lifecycle](frontend-sse-lifecycle.md) — the canonical EventSource lifecycle every SSE-consuming React component must mirror.
- [frontend-sse-polling-fallback](frontend-sse-polling-fallback.md) — SSE polling-fallback anti-pattern: onerror starts polling never stopped after auto-reconnect → permanent double-fetch.
- [sse-broadcaster-patterns](sse-broadcaster-patterns.md) — EventBroadcaster fan-out review points: set-iteration safety, silent Redis-drop, the justified no-response_model exception.
- [warning_swallowed_on_unmount](warning_swallowed_on_unmount.md) — a form that sets a local warning THEN calls onSaved (closing the form) never shows the warning.

### Review hygiene & observability
- [observability-brick-a](observability-brick-a.md) — Brique A observability audit anti-patterns (queue/metrics/heartbeat/events + jobs/monitoring routers).
- [async_teardown_swallow](async_teardown_swallow.md) — async worker/task teardown that swallows all exceptions silently, hiding genuine crashes.
- [deletion_batch_residue](deletion_batch_residue.md) — on feature-purge batches, identifier-grep misses orphaned env vars + stale docstrings; check both explicitly.
- [stray_claude_dir_under_src](stray_claude_dir_under_src.md) — multi-agent batches can write agent-memory to `src/**/.claude/` (NOT gitignored); scan git status for it.
- [static-builder-method-order](static-builder-method-order.md) — static builders under pipelines/ put public `build` before private helpers (deviates from python.md); grade LOW/non-blocking, matches the local convention.
- [antipattern-chain-kind-raises](antipattern-chain-kind-raises.md) — StageCompiler chain/provider paths must validate a user kind against NodeRegistry.kinds BEFORE NodeRegistry.get (which raises KeyError); its contract is "nonsensical action = notice, never an exception". Fixed in P3, keep as a review heuristic.
- [selectable-flag-discovery-only](selectable-flag-discovery-only.md) — P6a SELECTABLE flag hides internal wiring nodes from the palette method-picker; discovery-surface ONLY, single chokepoint at NodeRegistry.catalog, must never leak into blob/graph/validation.

> Component-scoped memory lives with the component agents: **mcp** (`agent-memory/mcp/`) for the
> `src/mcp/` HTTP-client invariant + REST endpoint map; **bge-server** (`agent-memory/bge-server/`) for
> the `src/bge_server/` model host. This file holds the cross-cutting product rules.
- [Stages package method-order convention](stages-method-order.md) — static builder classes put the public entrypoint first, privates below; do not flag as a python.md violation
- [Translator drops artefact fields](translator-drops-artefact-fields.md) — a new Chunk/IR artefact field must also be set in worker translator.py ORM row, else the DB row silently uses server_default
- [Inert-scaffolding antipattern](inert-scaffolding-antipattern.md) — green tests + unchanged golden on a claimed BEHAVIOR fix is a signal to grep for consumers, not a pass; a truncated agent ships config/fields/helpers with no wiring
- [ColBERT late-interaction review](colbert-late-interaction-review.md) — content_colbert 3rd-vector: inner-prefetch filter placement, colbert=None byte-identity, colbert_dim-from-first-chunk fragility, flag-as-vector-presence proxy gap (one-way-door 500), metadata isolation
