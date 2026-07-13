# Backend Craftsman — Memory Index

The FastAPI web + data layer of the ACTIVE product `src/docforge-rework/` (soon renamed `docforge`):
`app/backend/` (routers pipelines/collections/documents/explorer/jobs/blobs) + the API-facing
`shared_libs` — the `services.db` façade (facades/ + clients postgresql/qdrant/s3) and `public_models`.
NOT the ingestion engine (that's `shared/libs/pipelines/` → **pipeline** agent).

## Ground truth (rework tree)

- Three roots: `shared/` (`shared_libs.*`), `app/` (`backend.*`), `worker/` (`backend.libs.*`).
  `config` (→ `RUNTIME_CONFIG`) imports FIRST in each entrypoint (registers the `shared_libs` alias +
  puts `backend/libs` on `sys.path`). New env var → the app's `app/config/runtime_config.py` (web-only)
  or `worker/config/runtime_config.py` (worker-only); shared vars in the common base config.
- Data layer is the façade `shared_libs.services.db` — routers/services call a facade, never a raw
  client. Tables at `shared/libs/services/db/postgresql/tables/` grouped by domain (authentication/
  blobs/chunks/collections/documents/ir/observability).
- Tests: `cd src/docforge-rework && uv run pytest tests/units` (subtree `api/`). Lint: `uv run ruff check .`; types: `uv run mypy .`.

## Rule checklist (enforce on your own output)

- FastAPI: `@auto_handle_errors` on every route (below `@router.verb`, above the fn); `response_model`
  always; no business logic in `router.py`; services via `CONTEXT.*` (never import instances in routes);
  `lifespan.py` `finally` guarded with `hasattr(CONTEXT, "attr")`; API prefix `/api/v1` defined once.
- Python: `LoggerClass.__init__(self)` on every instanciable class; no `print()`; log messages are
  f-strings; 4 labeled import sections; `# ====== Code Summary ======` header; `__init__.py` = sections
  + `__all__`; config via `RUNTIME_CONFIG` only (new var → the app's `config/runtime_config.py`).
- Return Pydantic models, never raw dicts. Verbose error handling: assert/emit exact HTTP codes.
- A broken pipeline blob comes back as DATA (`valid=false` + issues), never an HTTP error — fail-fast
  validation lives in the engine's `GraphValidator`, surfaced by the router.

## Anti-patterns (timeless — from past reviews)

- `collection_id` / any id passed positionally → silently `None` downstream. Always keyword.
- Missing `await` on async façade/repo methods (returns a coroutine, no warning).
- Returning a SQLAlchemy model needing relations outside the session → `DetachedInstanceError`;
  `await session.refresh(obj, attribute_names=[...])` first.
- `_IncludedRouter` wrapping means you must introspect the surface via `app.openapi()["paths"]`, NOT
  `app.routes`. See [[docforge-rework-explorer-api]].

## Topic files

- [API surface map](api-surface-map.md) — authoritative /api/v1 shape: routers, routes, prefix algebra, the SSE routes, the bytes route, files-return-URL-not-bytes distinction.
- [Auth keys-only model](auth-keys-only-model.md) — root account + permissioned API keys with per-collection capabilities; replaces the old grant/collaborator/impersonation model.
- [Collection sub-router wiring](collection-subrouter-wiring.md) — 3-step registration for a new per-collection sub-router + the discovery-overlay/capability pattern.
- [docforge-rework explorer API](docforge-rework-explorer-api.md) — explorer/blobs router wiring over the `shared_libs` db façade; chunk bulk-read seams; the `_IncludedRouter` introspection + S3 underscore-host gotchas.
- [Search overrides (Search Lab)](search-overrides.md) — ⚠️ STALE ERA (gone 2026-07): a retired `SearchPipelineEngine`/override-merge surface; current path is a direct facade call.
- [Hybrid search endpoint](hybrid-search-endpoint.md) — POST /collections/{id}/search: embeds the query with the collection's OWN embed node (reuses its hooks), names vectors via VectorNames constants, filters→Conditions, un-ingested guard in SearchFacade.
- [Enable/disable searchability](enable-disable-searchability.md) — reversible chunk/doc toggle: search-exclusion injected in SearchFacade (unbypassable), EnablementFacade flips payload via set_payload (never re-embed), is_indexed = "has a point", never-embedded → reindex_required.
- [Test backend import wiring](test-backend-import-wiring.md) — in `tests/units/api`, defer every `from backend...` import until the `fastapi_app` fixture has set `sys.path`; a module-top import fails collection with `ModuleNotFoundError: backend`.

- [Pipeline blob validation](pipeline-blob-validation.md) — `PipelineBlobValidator` is the single build+validate chokepoint; called on collection create/update AND before every document enqueue (stale stored blob → 422 naming the node, spends nothing).

## Boundary

Routers/services/façade-callers/config/models on the request→response path. Ingestion engine
(`shared/libs/pipelines/`) → **pipeline**. Schema/migrations → **migration-engineer**. UI → **frontend**.
Packaging → **docforge**. Hand non-trivial diffs to **code-reviewer**.

- [ColBERT third named vector wiring](colbert-named-vector.md) — content_colbert end-to-end: persistence (multivector, content-point-only, byte-bounded upsert) + search late-interaction re-score, flag off by default.
