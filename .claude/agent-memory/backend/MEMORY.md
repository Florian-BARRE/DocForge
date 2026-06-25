# Backend Craftsman — Memory Index

The FastAPI web + data layer: `src/docforge/app/backend/` + the API-facing `common_libs` (storage
repos, config, domain models, search/observability wiring). NOT the ingestion pipeline.

## Rule checklist (enforce on your own output)

- FastAPI: `@auto_handle_errors` on every route (below `@router.verb`, above the fn); `response_model`
  always; no business logic in `router.py`; services via `CONTEXT.*` (never import instances in routes);
  `lifespan.py` `finally` guarded with `hasattr(CONTEXT, "attr")`; API prefix `/api/v1` defined once.
- Python: `LoggerClass.__init__(self)` on every instanciable class; no `print()`; log messages are
  f-strings; 4 labeled import sections; `# ====== Code Summary ======` header; `__init__.py` = sections
  + `__all__`; config via `RUNTIME_CONFIG` only (new var → `BaseRuntimeConfig` if shared, else per-app
  subclass + `services/docforge/.env`).
- Return Pydantic models, never raw dicts. Verbose error handling: assert/emit exact HTTP codes
  (415/413/422 admissibility → 429/409 resource → after dedup). See [[verbose-error-handling-convention]].

## Anti-patterns seen here (from past reviews)

- `collection_id` passed positionally → silently `None` in `enqueue_job`. Always keyword.
- Missing `await` on async repo methods (returns a coroutine, no warning).
- Typed Pydantic provider configs have FLAT fields post-refactor — no `.params`; use
  `cfg.model_dump(exclude={"id"})`. Registry params use `"name"` (not `"key"`) — drift 500s `/discovery`.
- Return SQLAlchemy model needing relations outside the session → `DetachedInstanceError`; `await
  session.refresh(obj, attribute_names=[...])` first.
- Adding a Pydantic field without the discovery overlay → UI can't surface it (`discovery/overlays.py`).

## API surface

- [API surface map](api-surface-map.md) — 12 routers / 38 routes; prefix algebra; the 2 SSE routes +
  1 bytes route; files/* return a pre-signed URL (not bytes); ingest error ladder. MCP mirrors 36 tools.
- [Discovery config_tree](discovery-config-tree.md) — recursive schema-driven describer (CHUNK D1);
  auto_import must use `common_libs.providers.*` (legacy `libs.providers.*` silently fails); field→
  category glue; ConfigNode/ProviderChoice mutual forward refs need model_rebuild; ADDITIVE to flat.

## Brique D (resource admission) — post-budget-purge

Budget/spend was fully removed (2026-06-25); only the **capacity (429)** path survives. `ResourceAdmitter`
gates on queue depth + global/per-collection in-flight only (no 409). Per-collection limit = `max_in_flight`
column on `collection` (the only resource cap). `JobModel` has no `budget_spent`; `JobResponse` has no budget
field. Admission models (`ResourceLimits`/`AdmissionSnapshot`/`AdmissionDecision`) carry no budget fields.
Limits sub-router (`collections/{id}/limits`) GET/PUT only `max_in_flight` + `in_flight`. `job_repo` has no
`sum_budget_by_collection`; `update_status`/`mark_finished` take no `budget_spent`. Worker-side cost write
(`worker/libs/pipeline/orchestrator/*`, `s2_enrich`) is **pipeline-owned**, not backend.

## Boundary

You own routers/services/repos/config/models on the request→response path. Ingestion engine (S0→S6,
providers, chains) → **pipeline**. Schema/migrations → **migration-engineer**. UI → **frontend**.
Packaging → **docforge**. Hand non-trivial diffs to **code-reviewer**.
