# Research Brief — Retrieval Observability + Retrieval-Quality Evaluation

> RESEARCH ONLY. This is a relevé (current-state facts + anchors + design options/risks), not a
> design. Active tree: `src/docforge/`. Plan phase consumes this directly.

## FEATURE

Make DocForge's SEARCH pipeline quality **measurable and non-regressable** without adding a
generation layer (retrieval-only, per CLAUDE.md invariant 1 — IR canonical / no generation). Three
independent sub-features investigated:

1. Per-search telemetry (Prometheus `docforge_search_*` series, graftable without breaking node purity).
2. Feedback capture (`POST /search/feedback` + a query-log table) enabling offline nDCG/MRR/CTR.
3. A retrieval-quality regression gate built on the existing `tests/rag_eval/` harness.

## STAGES AFFECTED

`search` (app-side, INLINE via `SearchRunner`/`FlowEngine`, NOT a graph-engine ingest stage) +
`backend` (routers, metrics, migrations). None of the 7 INTAKE→EMBED ingest stages are touched.

---

## AREA 1 — PER-SEARCH TELEMETRY

### Current-state facts

- **Execution path**: `SearchRouter.search_collection` (`src/docforge/app/backend/routers/search/router.py:37-150`)
  → `SearchService.search` (`src/docforge/app/backend/libs/search/service.py:138-217`) → resolves
  the blob (`__resolve_blob`, service.py:84-119, stock default vs. collection's own `collection.search`
  blob, healed via `SearchBlobNormalizer`) → `SearchRunner.run` (`src/docforge/app/backend/libs/search/runner.py:185-270`).
- **`SearchRunner.__init__`** (runner.py:75-84) constructs `FlowEngine(trace_level=TraceLevel.OFF)`
  — **explicit, commented invariant**: "Search runs INLINE in the request and DISCARDS the record,
  so it captures nothing — no per-hop trace work is spent (the ingest worker is the only trace
  consumer)" (runner.py:79-81). Confirms architecture.md's node-purity/trace-capture model applies
  identically to search, but **search does not persist any trace today** — it's an ingest-worker-only
  feature (`persist_execution_tree` lives in the worker, per architecture.md).
- **`NodeExecutionRecord`** (`src/docforge/shared/libs/pipelines/base/execution.py:98-138`) is
  produced by the engine for EVERY run **regardless of `trace_level`**: `node_id`, `kind`, `status`,
  **`duration_ms`** (always populated — not tiered by `TraceLevel`), `error`, `usage`, `score` (lifted
  from `ScoredOutput.score` when the node's family is `scored`) are structural and **survive
  `TraceLevel.OFF`**; only `resolved_input`/`output`/`input_summary`/`output_summary` are tiered by
  trace level (execution.py:107-116, confirmed against architecture.md's "Capture de trace" section).
  **This means the record tree the runner currently discards already carries per-node timing +
  score for free — no engine change is needed to get per-node latency; TraceLevel.OFF already pays
  for it.**
  - `SearchRunner.run` currently uses this record ONLY for `__failed_node_reason`/`__failed_error_type`
    (runner.py:86-132, walked only on `output is None`) and passes it to `UsageSummer.summarize`
    (runner.py:264, for LLM rewrite/HyDE cost metering) — **then discards it** (`finally: self._pool.release(...)`,
    runner.py:267-270). The record is never inspected on the SUCCESS path beyond usage summing.
- **`SearchResult`** (`src/docforge/shared/libs/public_models/search/result.py:15-33`): `query`,
  `hits: list[Hit]`, `debug: dict | None`. The `debug` bag is populated ONLY by the terminal
  `DeliverHitsNode` (`src/docforge/shared/libs/pipelines/search/nodes/deliver/hits/core.py:61-70`):
  `{"hit_count": len(hits)}` plus `debug["degraded"]` (a string note, e.g. "dense axis unavailable")
  carried from `RankedHits.degraded` ← `CandidateSet.degraded` ← `EncodedQuery.degraded`
  (propagation chain: `encode/collection/core.py` → `retrieve/hybrid/core.py:92-96` →
  `postprocess/hydrate/core.py` → `deliver/hits/core.py:66-67`). **No candidate counts, no per-stage
  timings, no fusion-source breakdown are in `debug` today** — only `hit_count` and an optional
  `degraded` string.
  - `Candidate.source` (`src/docforge/shared/libs/public_models/search/elements.py:11-34`) exists as
    a provenance field, but `CollectionReadPortImpl.hybrid_search` stamps EVERY candidate with the
    same constant `_RETRIEVAL_SOURCE = "hybrid"` (`src/docforge/app/backend/libs/search/read_port.py:29,101`)
    — retrieval is ONE server-side Qdrant hybrid call (dense+sparse fused server-side by
    RRF/DBSF inside Qdrant), so **there is no per-branch (dense vs. sparse) candidate count available
    at the DocForge layer today** — Qdrant does the fusion internally and only returns the fused
    pool. Getting a dense/sparse contribution breakdown would require either (a) two separate Qdrant
    queries (dense-only, sparse-only) purely for instrumentation — extra store round-trips on the hot
    path — or (b) reading whatever per-branch debug Qdrant's hybrid/query API optionally returns
    (needs verification against the installed Qdrant client version — not confirmed in this pass).
  - **Fusion nodes** (`src/docforge/shared/libs/pipelines/search/nodes/fuse/placeholders.py:36-60`,
    `FuseRrfNode`/`FuseWeightedNode`) are `PlaceholderNode`s (`SELECTABLE=False`, bodies raise) for a
    FUTURE retrieve-decompose phase (P3, per the placeholder's own docstring) — fusion today happens
    **inside Qdrant**, not as a graph node, so there is no node-level fusion score/contribution to
    trace even if trace_level were raised.
  - `RetrieveHybridConfig.fusion: Literal["rrf","dbsf"]` (retrieve/hybrid/core.py:24-34) is the only
    per-collection knob on fusion strategy (in the search pipeline blob, `extra="forbid"` via
    `NodeConfig`) — confirms fusion strategy IS already per-collection blob config, not an env flag.
  - `score_kind` on `SearchResponse` (`src/docforge/app/backend/routers/search/models.py:220-228`)
    already labels what a hit's score means (`rrf_fusion`/`dbsf_fusion`/`cross_encoder_rerank`) —
    this is the closest existing "fusion source" signal, but it's a query-shape label, not a
    per-candidate contribution metric.
- **Existing metrics infra** (the pattern to mirror exactly):
  - `DocForgeMetrics` (`src/docforge/app/backend/libs/metrics/collectors.py:12-58`) — a **static
    holder class**, every `Counter`/`Histogram`/`Gauge` created **once at import time** as a class
    attribute, on the **default `prometheus_client` registry** (no custom registry). All series
    prefixed `docforge_` (`docforge_http_requests_total`, `docforge_arq_queue_depth`, etc.) —
    confirms the `docforge_search_*` self-scoping the task specifies is exactly this convention.
  - Two feed mechanisms exist side by side: (a) `HttpMetricsMiddleware` (http_middleware.py:56-164) —
    a **pure ASGI middleware**, stateless, feeds Counters/Histograms **passively per-request** with
    NO async I/O of its own (labels only method/route-template/status, bounded cardinality via
    `_KNOWN_METHODS`/`_UNMATCHED`/`_GATE_REJECTED` sentinels); (b) `MetricsService` (service.py:27-133) —
    an async service that **refreshes Gauges lazily AT SCRAPE TIME** (`render()` called from the
    `/metrics` route, service.py:56-70), each gauge refresh independently best-effort + bounded by
    `scrape_timeout_seconds` so a degraded store never wedges a scrape (service.py:72-129).
  - `/metrics` router (`src/docforge/app/backend/routers/metrics/router.py:23-41`) — registered
    **OUTSIDE `/api/v1`** (auth/rate-limit middlewares only gate `/api/v1/*`), `include_in_schema=False`
    (never touches the OpenAPI/SDK-parity snapshot), gated by `RUNTIME_CONFIG.METRICS_ENABLED`
    (`app/config/runtime_config.py:215`, documented `docs/configuration.md:65-66`) → 404 when off.
  - **Confirmed**: a per-search metric emission call belongs at the **app-side boundary**
    (`SearchRunner.run` or `SearchService.search` or the router), analogous to `HttpMetricsMiddleware`
    being OUTER to routing rather than inside a route handler — **never inside a search node**. Node
    purity (architecture.md: "Un node est pur... zéro I/O DB/S3") extends to metrics emission by the
    same logic used for persistence: nodes may be read via an injected capability (`bind()`) but never
    write/emit as a side effect. `SearchRunner.run` already has the one place that (a) always executes
    for every search (success AND failure paths converge there before `finally: self._pool.release`)
    and (b) already holds the full `NodeExecutionRecord` tree post-execute — making it the natural
    single emission point for BOTH the stage-latency histogram (walk `record.children` for
    `duration_ms`+`kind`) and outcome counters (zero-result via `len(result.hits)`, `degraded` flag
    via `result.debug`). The router is a secondary option (has `SearchRequest.search_in`/`filters`
    shape info the runner does not) but duplicates work already done once in the runner/service.
- **Telemetry overlay posture**: `compose/overlays/compose.telemetry.yml` wires Prometheus/Loki/Alloy/
  Grafana as an **opt-in add-on**, never baked into a scenario (confirmed by CLAUDE.md's compose
  section + the `telemetry-observability` project memory: Alloy replaced Promtail 2026-09-15,
  dashboards use `${DS_PROMETHEUS}`/`${DS_LOKI}` vars, prometheus runs with
  `--web.enable-remote-write-receiver`). A new `docforge_search_*` series requires NO overlay change
  — it renders through the SAME `/metrics` endpoint the moment it's registered on the default
  registry; only the Grafana dashboard JSON (not investigated in this pass) would need new panels.
  No direct OpenTelemetry SDK usage was found anywhere in `app/backend/libs/metrics/` — the posture
  is **plain `prometheus_client` + Alloy log/metric scraping**, not an OTel SDK integration; adding
  OTel would be a new posture, not an extension of the existing one (external-docs pull below).

### Design options (Area 1)

| Option | Where metric emission lives | Trade-off |
|---|---|---|
| A. Emit inside `SearchRunner.run` (after `FlowEngine.execute`, before `finally`) | Runner | Single choke point for every caller (router + any future caller e.g. MCP/CLI direct search); already holds the record tree + `result`; symmetric with how `UsageSummer.summarize` already runs there. **Recommended.** |
| B. Emit inside `SearchService.search` | Service | Has collection_id (a label risk — cardinality! must NOT label by collection_id) but no advantage over A; adds a second place that must agree on label names. |
| C. Emit inside the search router | Router | Has HTTP-facing shape (request `search_in`) but is one layer further from the engine's own timing record; would need to accept the return tuple then still walk `result.debug`/usage — no new information the runner lacks. |
| D. A dedicated `postprocess` search node that emits | A node | **Rejected** — violates node purity (architecture.md: nodes are pure, zero I/O); explicitly the thing the task asked to verify against. |

Label cardinality guard (mirrors `HttpMetricsMiddleware`'s bounded-label discipline, collectors.py):
a per-search histogram MUST NOT label by `collection_id` (unbounded) — label by node `kind` (bounded,
registry-sized) for stage latency, and keep outcome counters label-free or labelled only by a bounded
enum (e.g. `fusion` strategy: `rrf`/`dbsf`, or `degraded`: true/false).

Candidate new series (naming mirrors `docforge_http_*`):
- `docforge_search_requests_total` (Counter, no labels or `{degraded}` only) — a run started/finished.
- `docforge_search_duration_seconds` (Histogram, label `stage`=node kind, from `record.children`
  walked exactly like `SearchRunner.__failed_node_reason` already walks the tree, replacing the
  early-return with a full traversal collecting `(kind, duration_ms)` pairs).
- `docforge_search_zero_result_total` (Counter) — `len(result.hits) == 0`.
- `docforge_search_degraded_total` (Counter) — `result.debug.get("degraded")` is truthy.
- Fusion-source-contribution counter is **NOT cleanly obtainable today** (see current-state fact
  above) — flagged as an open question, not a straightforward metric to add without a retrieval-path
  change (extra Qdrant round-trip or a Qdrant client version bump for branch-level debug info).

### Risks (Area 1)

- A stage-latency histogram walking `record.children` on every search adds CPU work on the hot,
  sub-second inline path — must be O(tree size), cheap (no serialization, only `duration_ms`+`kind`
  reads), same cost class as `__failed_node_reason`'s existing walk.
- Must NOT re-introduce a payload/label cardinality leak (e.g. never label by `node_id` if node ids
  can be user-influenced via a custom search blob — use `kind`, which is registry-bounded, never
  `node_id`, which a stored custom blob could name arbitrarily).
- `TraceLevel.OFF` is a deliberate choice for the inline hot path (comment at runner.py:79-81) —
  raising it to `SHAPE`/`FULL` for search (to get `input_summary`/`output_summary`) would add real
  work per request; the plan should keep `TraceLevel.OFF` and rely only on the structural fields
  (`duration_ms`, `score`, `usage`) that already survive it, per architecture.md's own framing.

---

## AREA 2 — FEEDBACK / ONLINE METRICS

### Current-state facts

- **No query log or feedback capture exists today.** Exhaustive grep for
  `query_log|search_log|SearchLog|QueryLog|search_feedback|feedback` across `src/docforge/**/*.py`
  (excluding `__pycache__`/`tests/`) returns exactly one unrelated hit
  (`app/backend/routers/pipelines/router.py`, an incidental word match, not a feature). Confirmed via
  `find`: no `query_log`/`search_feedback` table under
  `src/docforge/shared/libs/services/db/postgresql/tables/`.
- **Search router** lives at `src/docforge/app/backend/routers/search/router.py` (only
  `POST /collections/{collection_id}/search`, no other search endpoint) — a sibling
  `POST /collections/{collection_id}/search/feedback` (or `/search/feedback`) would live in the same
  router file/folder (`routers/search/`), following the existing helpers.py/models.py split.
- **Auth/scoping pattern**: `require(Capability.SEARCH)` dependency
  (`src/docforge/app/backend/libs/auth/permissions.py:21-31`, `router.py:34`) — `Capability` is a
  coarse `StrEnum` (`READ/WRITE/SEARCH/CREATE/ADMIN`); a scoped API key's `KeyPermissions.collections`
  is either `["*"]` or an explicit per-collection UUID allowlist (permissions.py:41-46). A feedback
  endpoint should reuse `Capability.SEARCH` (same class of action as searching) scoped by the
  `collection_id` path param exactly like the search endpoint — no new capability needed unless the
  plan phase decides feedback should be gate-able independently of search (open question).
- **Append-only audit-style table precedent**: `AuditLog`
  (`src/docforge/shared/libs/services/db/postgresql/tables/observability/audit_log.py:20-81`) is the
  closest existing shape for a query/feedback log: BIGINT `Identity` PK (not UUID — append-heavy,
  never FK'd, sequential insert locality), actor ids stored RAW with **no FK** (must survive actor
  deletion), indexed `(actor_*, created_at DESC)` and `(target_type, target_id, created_at DESC)` for
  read-path filters, `CreatedAtMixin`. A query-log table for feedback would likely mirror this shape:
  no FK to `chunk`/`document`/`collection` for the LOGGED ids (a query outlives a later-deleted chunk;
  the log is a historical fact), but SHOULD FK `collection_id` since a collection's rows must be
  reachable/deletable together with it (or follow `AuditLog`'s no-FK precedent if long-term
  cross-collection analytics matters more than cascade-delete cleanliness — **open question for the
  plan**).
- **Migration precedent to mirror**: `c9a4e1b7f302_add_idempotency_key_table.py`
  (`src/docforge/shared/migrations/versions/c9a4e1b7f302_add_idempotency_key_table.py:1-45`) shows the
  house style for a new append-only table migration: BIGINT `Identity` PK, `UNIQUE`/read-path indexes
  named per `NAMING_CONVENTION`, an extensive header comment explaining design choices + data-safety
  statement (STRICTLY ADDITIVE / reversible). The migration chain is single-head — the newest tail is
  `f6a3d8b2c1e7_add_job_token_cost_meter.py` (per `ls versions/`); a new migration's `down_revision`
  must point at the actual current head at plan time (re-check, chain moves).
- **`JobStageEvent`** (`.../observability/job_stage_event.py:22-141`) is the ingest-side per-node trace
  persistence table (materialized-path `node_path`/`depth`/`parent_path`/`item_index`/`score` +
  trace-payload columns `input_summary`/`output_ref`/etc.) — confirms the project's established
  pattern for "per-run node-level facts" persistence, useful as a structural precedent IF the plan
  decides a search run's node tree should also be persisted (it currently is NOT — Area 1 confirms
  `TraceLevel.OFF` discards it). Search's query-log table is a DIFFERENT concern (query + hit ids +
  usefulness signal, not a node trace) — do not conflate the two; `JobStageEvent` is cited here only
  as the nearest schema-design precedent, not as a table to extend.
- **Ripple surface for a new endpoint** (per `rules/methodology.md`'s coupling map row "a
  request/response model"): `docforge_sdk/tests/openapi_snapshot.json` (regenerated via
  `app/scripts/dump_openapi.py`, confirmed used by the `sdk-parity` gate job in `.github/workflows/gate.yml:281-306`)
  + the SDK mirror `docforge_sdk/docforge_sdk/models/search.py` +
  `docforge_sdk/docforge_sdk/resources/search.py` (the `_SearchSpecs` mixin pattern — pure
  `RequestSpec` builders shared by `AsyncSearch`/`SyncSearch`, confirmed at `resources/search.py:1-20`)
  + `docforge_sdk/tests/parity_map.py` (drift map) + `docs/rest-api.md` (new route must appear
  verbatim, enforced by `test_every_api_route_is_documented_in_rest_api_md`,
  `tests/units/coherence/test_doc_coherence.py:164-182`, which derives from the SAME committed
  snapshot — so the snapshot regen is the one ripple that satisfies BOTH the sdk-parity gate AND the
  doc-coherence ratchet transitively). MCP tool: `src/mcp/libs/tools/search.py` exists as the current
  search tool wrapper — a feedback tool would be a sibling addition there (MCP is a "pure HTTP client
  of the DocForge SDK" per CLAUDE.md's neighbouring-components section — no domain logic in MCP).
- **nDCG is NOT in `tests/rag_eval/metrics.py` today** — only `hit_at_k`, `recall_at_k` (a containment
  proxy, not true set-recall — see its own docstring caveat at `metrics.py:86-94`), and
  `reciprocal_rank`/MRR (`metrics.py:97-102`). A feedback-driven nDCG/CTR computation would be NEW code,
  not an extension of an existing offline metric — likely a new module (e.g.
  `app/backend/libs/search/` analytics helper, or an offline notebook/script reading the query-log
  table) since `tests/rag_eval/` is a TEST-tree module (imports fixtures, not meant to be imported by
  production code) — the plan should decide whether online-metric derivation is production code (a
  new admin/analytics endpoint reading the log) or an offline script, and where nDCG's discount
  formula gets its relevance grades from (the feedback endpoint only captures binary
  useful/not-useful per hit unless the plan asks for graded relevance).

### Design options (Area 2)

1. **What the feedback endpoint references**: `query text` (or its content hash, to avoid storing
   arbitrary-length free text redundantly per feedback event) + the returned `hit` ids
   (`chunk_id`s — the SDK/response model's stable identifier, `SearchHitModel.chunk_id`,
   `routers/search/models.py:119`) + which were marked useful — vs. round-tripping the full
   `SearchResponse` back. **Recommended**: client sends `{query, chunk_ids: list[str], useful_chunk_ids: list[str]}`
   (or a per-hit `{chunk_id, useful: bool}` list) — simplest schema, no server-side session/result
   caching needed, symmetric with how the search response already exposes `chunk_id` per hit.
2. **Table shape**: either (a) one row per feedback SUBMISSION (query + full hit-id array + useful
   subset as JSONB, mirroring `AuditLog`'s single-row-per-event shape), or (b) one row per
   (query, hit) PAIR (normalized, easier SQL aggregation for nDCG/CTR but more rows). Given the
   `AuditLog`/`JobStageEvent` precedent both favor a single denormalized JSONB-bearing row per event
   (not a fully normalized join table), **option (a)** matches house style; nDCG/MRR/CTR derivation
   would then unnest the JSONB at read time (Postgres `jsonb_array_elements`) or in a Python offline
   script — the plan phase should pick based on expected log volume.
3. **CTR** = clicks (`useful=true` submissions) / impressions (search runs) — impressions are NOT
   currently logged at all (Area 1's `docforge_search_requests_total` counter, if built, gives an
   AGGREGATE impression count but not a per-query-text joinable one); a true per-query CTR needs
   either the query log to double as the impression log (log every search AND every feedback,
   joined by a shared `query_id` the search endpoint would need to start returning) or accept CTR
   as an aggregate-only metric (Prometheus counter ratio, not a per-query breakdown). **This is a
   real design fork for the plan phase**, not resolvable from current code alone — flagged as an open
   question below.

### Risks (Area 2)

- Retrofitting a `query_id` onto `SearchResponse` (needed to correlate a later feedback POST with the
  originating search event, if impressions must be logged) is itself a response-model change with the
  full SDK/snapshot/MCP ripple even before the feedback endpoint exists — sequencing matters (impression
  logging may need to ship WITH or BEFORE the feedback endpoint, not after).
- A feedback endpoint that accepts arbitrary `chunk_ids` from the client without verifying they belong
  to the named collection is a potential cross-tenant data-shape leak vector (a malicious/buggy client
  submitting another collection's chunk ids into the log) — should validate the mapping at write time,
  mirroring the search router's existing filterability/target 422 gates.
- Storing raw query TEXT (vs. a hash) in a query log is a potential PII/sensitive-content retention
  concern for a document-intelligence product — precedent (`AuditLog`) stores structural facts (method/
  path/actor), not free-text bodies; the plan should consider a retention/GC policy symmetric to the
  existing `job`/`job_stage_event` age-based prune (per the `perf-audit remediation` release in
  gitStatus's recent commits — "age-based prune for the unbounded job/job_stage_event tables").

---

## AREA 3 — QUALITY REGRESSION GATE

### Current-state facts

- `tests/rag_eval/` layout (`src/docforge/tests/rag_eval/README.md:29-37`, confirmed on disk):
  `metrics.py` (pure, unit-tested, NO network/store/DocForge import — confirmed by its own header
  comment, `metrics.py:1-6`), `qasper.py` (loader, pulls from HuggingFace datasets-server HTTP API),
  `synthetic.py` (deterministic short-clause corpus, no network), `harness.py` (a thin
  `httpx`-based `DocForgeClient` REST client — `harness.py:22-172` — + `run_eval`/`compare_configs`
  eval loops, `harness.py:211-282`), `runner.py` (CLI entry point, `tests/rag_eval/runner.py:1-110`,
  invoked via `python -m tests.rag_eval.runner`), `test_metrics.py`/`test_synthetic.py` (serviceless
  unit tests), `test_rag_eval_live.py` (`@pytest.mark.live`, skips unless `DOCFORGE_TOKEN` is set AND
  the live API answers — confirmed `test_rag_eval_live.py:19-21`, `client_from_env`
  does a reachability+auth probe before returning a client, `harness.py:181-196`).
- **The `live` marker is registered and the gate deliberately excludes it**: `gate.yml`'s own header
  comment states explicitly "No docker IMAGE builds and no `-m live` test (which needs a running API)
  ever run here" (`.github/workflows/gate.yml:14`). The `docforge` gate job runs
  `pytest tests/units -q --cov=...` (gate.yml:62) — `tests/rag_eval/` is OUTSIDE `tests/units/` (it's
  a sibling of `tests/units/`, `tests/db/`), so **`test_metrics.py`/`test_synthetic.py` are not even
  collected by the current gate invocation** (the gate only globs `tests/units`) — confirmed by
  directory listing: `tests/rag_eval/` sits beside `tests/units/`, `tests/db/`. This means even the
  PURE, serviceless `metrics.py`/`synthetic.py` unit tests do NOT run in CI today; they are
  developer-run-only (`cd src/docforge && uv run pytest tests/rag_eval/test_metrics.py`, per the
  README) — a gap the plan phase should note as low-risk, low-cost to close regardless of the bigger
  golden-set question.
- **`db-tests` job** (gate.yml:64-107) spins a throwaway `postgres:16` service — the ONLY
  service-container job in the whole gate — for `tests/db -m db`. No Qdrant, no Redis, no BGE
  embedder, no worker container exists anywhere in `gate.yml`/`ci.yml`. A genuine retrieval-quality
  run (ingest → embed → Qdrant hybrid search) needs ALL of those (the full `compose.dev-cpu.yml`
  stack, per CLAUDE.md's dev command) — **far beyond what `db-tests`' single-Postgres pattern
  provides**. Standing up Qdrant+Redis+BGE+worker as GH Actions `services:` containers is possible in
  principle (they're all plain Docker images) but is a materially heavier, slower job than anything
  in the current gate (BGE-M3 model load alone; the bge-server gate job already isolates torch's
  weight for exactly this reason, gate.yml:148-153) — this pushes toward a SEPARATE, not
  every-PR, workflow.
- **Coherence ratchets** (`tests/units/coherence/test_doc_coherence.py`) are STRING/PATH-level checks
  only (node-kind-in-doc, stage-name-in-doc, dead-path-refs, compose-naming, route-in-doc,
  env-var-in-doc) — explicitly scoped narrow ("Deliberately narrow: only objective, string-level facts
  are checked... Prose accuracy stays a human/review concern", `test_doc_coherence.py:19-20`). **There
  is no numeric/threshold ratchet pattern in this file to mirror** — a retrieval-quality gate (hit@k
  ≥ threshold) is a DIFFERENT ratchet shape (a live numeric assertion against a golden set, not a
  static-doc-inventory check) and has no existing sibling to copy structurally; it is closer in spirit
  to `test_rag_eval_live.py`'s existing `assert report.metrics.hit_at[10] > 0.0` (a live, stack-needing
  assertion) than to anything in `coherence/`.
- No nightly/scheduled/`workflow_dispatch` CI workflow exists in `.github/workflows/` today (only
  `ci.yml`, `gate.yml`, `release-sdk.yml`, confirmed by directory listing) — a live retrieval-quality
  job would be the FIRST scheduled/opt-in workflow in this repo, not an extension of an existing one.

### Design options (Area 3)

| Option | Mechanism | Verdict |
|---|---|---|
| A. Golden-set metrics run SERVICELESS in `gate.yml` (every PR) | Would need pre-computed/fixture ranked-chunk lists (bypassing real retrieval) fed straight into `metrics.py`'s pure functions | **Does not test retrieval** — it would only guard `metrics.py`'s own arithmetic (already covered by `test_metrics.py`). Cannot catch a real chunker/embedder/fusion regression. Rejected as the PRIMARY gate; still worth doing as a cheap smoke (see the `tests/units` collection gap noted above) but is not "the" regression gate the task asks for. |
| B. A new opt-in CI job (scheduled and/or `workflow_dispatch`, and/or PR-label-gated) that stands up the real stack (`compose.dev-cpu.yml` or a leaner services-only compose) and runs `runner.py`-equivalent logic against a fixed golden query set with an asserted-not-to-regress threshold | New workflow file, mirrors `db-tests`' `services:` pattern but multiplied (postgres+redis+qdrant+bge_server, or reuse `compose.dev-cpu.yml` via `docker compose up`) | **Recommended** — matches the "separate opt-in CI job" the task anticipated; cost/slowness is real (model load, ingestion wait) so PR-blocking-on-every-push is likely wrong; nightly/scheduled or manual-dispatch with a stored baseline (a committed JSON of last-known hit@k/MRR per corpus/config) is the natural shape, diffed against a tolerance band. |
| C. Fold a MUCH smaller synthetic-only golden set (the existing `synthetic.py` regulatory corpus, already deterministic/no-network) into the EXISTING `db-tests`-style job by additionally standing up Qdrant+BGE (skip QASPER's network fetch entirely) | Extends `db-tests` job or a new sibling | A middle ground: keeps network-fetch (QASPER) out of CI (already a documented risk in the README — "pulled page-by-page from the HuggingFace datasets-server HTTP API") while still exercising the real embed+retrieve path on deterministic synthetic docs. Still needs BGE model weights pulled/cached in CI (cost), and still can't run in the fast/serviceless `docforge` job. Worth flagging to the plan as the lowest-cost REAL option, distinct from B's full QASPER sweep. |

### Risks (Area 3)

- QASPER's HuggingFace network dependency is a flakiness/determinism risk for ANY CI use (README
  itself frames this as a live-only, developer-run concern) — a CI gate should prefer the
  `synthetic.py` corpus (deterministic, no network) for the threshold-asserted path, and treat QASPER
  sweeps as a manual/nightly-only diagnostic, not a merge-blocking signal.
- BGE-M3 model weight download/load cost (already isolated into its own gate job for the SAME reason,
  gate.yml:148-153 comment) makes any stack-based retrieval job meaningfully slower than the rest of
  the gate — must not be wired into the PR-blocking `ci.yml` path without an explicit cost/latency
  trade-off decision (this is a "consult the user" item per orchestrator.md's contract — a CI-cost /
  merge-latency trade-off the code doesn't settle on its own).
- A numeric regression threshold (e.g. "hit@10 must not drop below 0.85") needs a BASELINE artifact
  someone commits and updates deliberately when a legitimate pipeline change shifts the number — the
  plan must specify where that baseline lives (a committed JSON next to `tests/rag_eval/`?) and the
  update ritual (who/when bumps it), or the gate will either never fire (baseline too loose) or block
  every legitimate retrieval improvement (baseline too tight, never revisited).

---

## NEW FILES NEEDED (indicative — plan phase finalizes)

- `src/docforge/app/backend/libs/metrics/search_metrics.py` (or extend `collectors.py`) — the
  `docforge_search_*` series + the record-tree walker helper.
- `src/docforge/shared/libs/services/db/postgresql/tables/observability/search_feedback.py` (or
  `query_log.py`) — the new table, following `AuditLog`'s shape.
- `src/docforge/shared/migrations/versions/<new_rev>_add_search_feedback_table.py`.
- `src/docforge/app/backend/routers/search/` gains a feedback route (in `router.py`) + request/response
  models (in `models.py`) — no new package needed, same router folder.
- `src/docforge_sdk/docforge_sdk/models/search.py` (extend) + `resources/search.py` (extend
  `_SearchSpecs`) for the new endpoint.
- `src/mcp/libs/tools/search.py` (extend, or a sibling `search_feedback.py`) for the MCP tool.
- A new `.github/workflows/retrieval-quality.yml` (Area 3, option B) — separate from `gate.yml`.
- Possibly `src/docforge/tests/rag_eval/golden.py` or a committed `tests/rag_eval/data/golden_baseline.json`
  (Area 3 baseline artifact).

## MODIFIED FILES

- `src/docforge/app/backend/libs/search/runner.py` (`SearchRunner.run`) — emit metrics after
  `FlowEngine.execute`, before `finally`.
- `src/docforge/app/backend/libs/metrics/collectors.py` — new series definitions (if not split out).
- `src/docforge/app/backend/routers/search/router.py`, `models.py`, `helpers.py` — feedback endpoint.
- `docs/configuration.md` — any new `SEARCH_*`/`METRICS_*` env var (if the plan adds one, e.g. a
  feedback-log retention window) MUST be documented here (coherence ratchet enforces this).
- `docs/rest-api.md` — the new feedback route (coherence ratchet enforces this transitively via the
  snapshot).
- `docforge_sdk/tests/openapi_snapshot.json` (regenerated, not hand-edited) +
  `docforge_sdk/tests/parity_map.py`.
- `src/docforge/PIPELINE.md` — likely NOT touched (search pipeline nodes/families are unchanged by
  Areas 1/2; only touch it if Area 3 or later work adds a real `fuse` node, which is out of this
  feature's scope).
- `.claude/rules/architecture.md` — if the plan formalizes "metric emission lives at the
  runner/router boundary, never in a node" as a named invariant (recommended, since this research
  explicitly verified and stated it — the auto-improvement protocol in `orchestrator.md` would want
  this captured so a future agent doesn't have to re-derive it).

## NEW DEPENDENCIES

None identified. `prometheus_client` is already a dependency (used by `collectors.py`). No new
package needed for Areas 1-2. Area 3 needs no new Python dependency either (`httpx` already used by
`harness.py`); the new CI workflow needs whatever Docker images the dev compose scenario already
pulls (no new image).

## NEW CONFIG

- Per-collection blob config: **none required for Area 1** — metrics emission is a cross-cutting
  app-side concern, not a per-collection knob (it always fires, like `HttpMetricsMiddleware`).
- `RUNTIME_CONFIG` candidates (env, NOT per-collection, following `METRICS_ENABLED` precedent):
  none strictly required to ship Area 1 (reuses the existing `METRICS_ENABLED` gate on `/metrics`
  itself) — a `SEARCH_METRICS_ENABLED` sub-flag is an option if the plan wants search metrics
  independently toggleable from HTTP metrics, but this is a genuine design choice, not a fact.
  Area 2 may need a feedback-log retention window (e.g. `SEARCH_FEEDBACK_RETENTION_DAYS`) mirroring
  the recent `job`/`job_stage_event` age-based prune precedent (gitStatus recent commit
  `7eeb003d perf(worker): age-based prune for the unbounded job/job_stage_event tables`).

## MIGRATION NEEDED

Yes — Area 2 only. One new Alembic migration adding the query/feedback log table (single-head chain,
current tail `f6a3d8b2c1e7_add_job_token_cost_meter.py` at research time — **re-verify the actual head
at plan/implement time**, the chain moves). Areas 1 and 3 need no schema change.

## KEY CONSTRAINTS

- Retrieval-only: no generation layer added anywhere (Areas 1-3 are all measurement/logging, not
  answer synthesis) — consistent with CLAUDE.md invariant 1.
- Node purity: metric emission and feedback-write logic MUST live at the app-side
  runner/service/router boundary, never inside a `shared_libs.pipelines.search.nodes.*` node
  (verified explicitly in Area 1 above).
- Per-collection config stays in the blob (`extra="forbid"` `NodeConfig`s) for anything that is a
  RETRIEVAL BEHAVIOR knob (e.g. fusion strategy already is); telemetry/feedback plumbing is
  cross-cutting infra config and belongs in `RUNTIME_CONFIG`/env, mirroring `METRICS_ENABLED` — do
  not conflate the two config surfaces.
- Bounded label cardinality on every new Prometheus series (never `collection_id` or a free-form
  `node_id` from a custom stored blob as a label).
- Auth: a new feedback endpoint scopes by `collection_id` under `Capability.SEARCH` like the search
  endpoint, per the existing scoped-API-key model (`KeyPermissions.collections`).
- Don't duplicate the existing token/cost meter (`SearchCostModel`/`UsageSummer`) — Area 1's new
  series are about LATENCY/OUTCOME, not spend, which is already surfaced.
- `sdk-parity` + `tests/units/coherence` ratchets are mechanical gates already in CI — any new route/
  env var MUST regenerate the snapshot and update `docs/rest-api.md`/`docs/configuration.md` in the
  same wave, or the gate goes red (this is enforced, not optional).

## OPEN QUESTIONS

1. **Fusion-source contribution metric**: is a dense-vs-sparse candidate-count breakdown worth the
   extra Qdrant round-trip(s) it would require (today's single hybrid call doesn't expose it), or
   should Area 1 ship without it and rely on `score_kind` + the `fusion` config label alone? (Needs a
   Qdrant client capability check not completed in this research pass.)
2. **Area 2 impression logging**: does CTR need to be joinable per-query (requiring a new `query_id`
   returned by `POST /search` and threaded through to the feedback log — a `SearchResponse` change
   with its own full ripple) or is an aggregate CTR (Prometheus counter ratio) sufficient for V1? This
   changes whether Area 1 and Area 2 must ship together or can be sequenced independently.
3. **Query-log FK strategy**: should the feedback/query-log table FK `collection_id` (cascade-delete
   clean) or follow `AuditLog`'s no-FK, survive-actor-deletion precedent? Depends on whether
   cross-collection longitudinal analytics matters more than delete-cascade hygiene.
4. **Raw query text retention**: store verbatim query text, a hash, or both (hash for dedup/join,
   text behind a separate opt-in/redactable column)? A PII/retention policy decision, not a technical
   one — needs a product-level call similar to the `product-not-dsi-scoped` memory's stance on
   optional add-ons.
5. **Area 3 gate cost/latency trade-off**: is a nightly/scheduled full-stack retrieval-quality job
   acceptable, or does the user want it `workflow_dispatch`-only (manual, on demand)? Per
   `orchestrator.md`'s consultation contract this is a CI-cost trade-off the code doesn't resolve on
   its own — ask before the plan commits to a schedule.
6. **Golden-set corpus for Area 3**: reuse `synthetic.py` (deterministic, no network — recommended)
   vs. a curated fixed QASPER slice pinned/cached to avoid live HuggingFace fetches in CI (would need
   the slice vendored into the repo, a new data-retention/size question for `tests/rag_eval/data/`
   which is currently git-ignored).
7. **nDCG's relevance grades**: the feedback endpoint as scoped only captures binary
   useful/not-useful — is binary relevance acceptable for nDCG (degenerates towards a form close to
   MAP), or does the plan want graded relevance (e.g. a 0-3 usefulness scale), which changes the
   feedback request schema?
8. Should the `docforge_search_*` Histogram/Counter definitions live in `collectors.py` directly
   (extending the existing static holder) or in a new sibling file — purely a code-organization call
   for the plan, general.md's ~150-200 line file-size guidance may push towards splitting given
   `collectors.py` is already at 58 lines and would roughly double.
