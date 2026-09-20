# Implementation Plan — Retrieval Observability + Retrieval-Quality Regression Gate

> DESIGN ONLY. Consumes `docs/rpi/retrieval-observability/research.md` (current-state facts + anchors).
> Active tree: `src/docforge/`. Every file:line anchor below was re-read and verified against the tree
> at plan time (commit `c9535c9f`); anchors move — re-confirm the exact line before editing.

## FEATURE

Make the SEARCH pipeline's behaviour **observable per request** (Axe 1) and its retrieval quality
**non-regressable** (Axe 3), with zero generation layer and zero node-purity violation.

**Axe 2 (feedback capture + query log + online nDCG/CTR) is OUT OF SCOPE — DEFERRED.** Nothing in
this plan pre-empts it: no `query_id` is added to `SearchResponse`, no table, no migration, no new
route. When Axe 2 is picked up it still owns research OQ2/3/4/7 (impression-join sequencing, FK
strategy, raw-query-text retention, graded vs binary relevance). The per-request probe + emitter
designed in Axe 1 is deliberately shaped so an impression counter could later reuse it.

## STAGES AFFECTED

`search` only (app-side, INLINE via `SearchRunner` — no arq) + `backend` metrics + CI. **None** of the
7 INTAKE→EMBED ingest stages is touched. No migration anywhere in this plan.

---

## Constraints honoured (restated, because each one shaped a decision below)

| Constraint | How this plan honours it |
|---|---|
| Retrieval-only, no generation | Everything added is measurement (counters/histograms) or evaluation. No answer synthesis. |
| Search runs INLINE (no arq) | All emission is synchronous, O(nodes) + O(top_k), on the request path; every emission is best-effort and wrapped so it can never fail a search. No background task is spawned on the request path. |
| Node purity — zero I/O in a node | Emission lives in `SearchRunner` (app-side). Extra retrieval round-trips live in `CollectionReadPortImpl` (app-side). A node only ever FORWARDS its own config to the injected capability, exactly as it already forwards `fusion` (`retrieve/hybrid/core.py:82-88`). **No node imports `prometheus_client`.** |
| Telemetry = opt-in overlay, `docforge_`-scoped | Every series is `docforge_search_*` on the default `prometheus_client` registry, so it renders through the existing `MetricsService.render()` → `generate_latest()` (`app/backend/libs/metrics/service.py:56-70`) and the existing `/metrics` route with **no compose change** and **no `MetricsService` change**. |
| Per-collection behaviour in the blob (`extra="forbid"`) over env flags | The one behaviour knob added (the dense/sparse breakdown) is a field on `RetrieveHybridConfig`, not a `RUNTIME_CONFIG` var and not a request flag. |
| Multi-tenant auth | No new endpoint, no new capability. The breakdown knob is writable only by whoever can write `collection.search` (`Capability.WRITE`), not by any `Capability.SEARCH` caller. |
| Don't duplicate the token/cost meter | Nothing here touches `UsageSummer`/`SearchCostModel` (`runner.py:264`). The new series are LATENCY/OUTCOME/SHAPE only — never spend. |
| No new dependency | `prometheus_client` and `httpx` are already dependencies. |

---

# SLICE ORDER

1. **3A** — collect the pure `tests/rag_eval` units in the gate (tiny; makes 3B's diff helper testable in the fast serviceless suite).
2. **1A** — per-search telemetry at the runner boundary (the headline value; zero API ripple).
3. **1B** — opt-in dense-vs-sparse fusion breakdown (needs 1A's probe + emitter).
4. **3B** — the non-blocking retrieval-quality workflow + gate helper + committed baseline (heaviest; benefits from 3A collecting its unit test).

Each slice is a complete vertical (producer + consumer + guard) and is independently shippable.

---

# SLICE 3A — collect the serviceless rag_eval units in CI

**Problem (verified).** `gate.yml:62` runs `uv run pytest tests/units -q --cov=…`. `tests/rag_eval/`
is a SIBLING of `tests/units/` (confirmed by directory listing), so `tests/rag_eval/test_metrics.py`
and `test_synthetic.py` — both pure, serviceless, network-free (`metrics.py:1-6` header) — are **never
collected in CI today**. They are developer-run-only.

### Modified files

| File | Change |
|---|---|
| `.github/workflows/gate.yml` | In the `docforge` job, AFTER the existing "Unit suite" step (`gate.yml:57-62`), add a step: `name: RAG-eval pure units (serviceless)` / `run: uv run pytest tests/rag_eval -q -m "not live"`. |
| `src/docforge/CLAUDE.md` → repo `CLAUDE.md` Commandes block | Add the copy-pasteable command next to the existing test bullets: `uv run pytest tests/rag_eval -q -m "not live"` (CLAUDE.md commands must be executable as written; `tests/rag_eval` exists, so `test_claude_md_referenced_paths_exist` stays green). |

**Why a separate step and not folded into the `tests/units` invocation:** the existing step is
coverage-gated and scoped `--cov=app --cov=worker --cov=shared`; `tests/rag_eval` is a test-tree
module that would muddy neither coverage nor attribution if kept apart. One step = one failure
attribution, which is gate.yml's own established style (cf. the frontend job's separate `tsc` step).

**`-m "not live"` is required**, not decorative: `test_rag_eval_live.py` is marked `live` and would
otherwise be collected (it self-skips on an unset `DOCFORGE_TOKEN`, but relying on a self-skip in CI
is exactly the kind of implicit behaviour the gate should not depend on).

### Ripples

- `.github/workflows/**` → YAML parse + re-read `needs`/`permissions`/`if`. **This is not a release-flow
  change** (gate.yml is `workflow_call`-only; the step is additive inside an existing job), so the
  "never push a release-flow change blind" rule (methodology.md, lesson 0.14.5→0.14.46) does not bite.
- CLAUDE.md edited → `scripts/backup-claude.sh` is NOT triggered (that ripple is for `.claude/**`);
  but see 1A, which does edit `.claude/rules/architecture.md`.
- SKIPPED: PIPELINE.md, SDK snapshot, migrations, compose, docs/configuration.md — nothing of theirs is touched.

### Guard

The step IS the guard: it turns a currently-uncollected suite into a red/green CI signal. No new test
file. Verification = the step passes locally with the same command.

---

# SLICE 1A — per-search telemetry at the runner boundary

## Design decisions (with rationale)

**D1. Emission point = `SearchRunner.run`'s `finally`, first statement, before `self._pool.release`
(`runner.py:267-270`).** The research brief recommended "after `FlowEngine.execute`, before the
`finally`". Refined deliberately: the four failure paths (`runner.py:239-253`) all `raise` INSIDE the
`try`, so an emission placed at the end of the `try` would observe SUCCESS RUNS ONLY — and latency
observability matters most on a timeout/unavailable run. Emitting as the `finally`'s first statement
covers success, `SearchRunError`, `SearchRunTimeout` and `SearchUnavailableError` uniformly. It is
still the single choke point every caller (router today, MCP/CLI tomorrow) passes through, exactly
per research option A.

**D2. Emission is wrapped in its own `try/except Exception` that logs a warning and never re-raises.**
Non-negotiable: an exception raised inside a `finally` would MASK the run's real exception (turning a
precise `SearchRunTimeout` into a metrics stack trace) and would also skip `self._pool.release`,
leaking a pooled graph. Mirrors `MetricsService`'s established best-effort posture
(`service.py:72-129`: "a degraded store never wedges a scrape").

**D3. `TraceLevel.OFF` stays. Confirmed sufficient for per-node latency.** Verified at
`execution.py:98-138` + `engine/core.py:177-189`: `node_id`, `kind`, `status`, `duration_ms`, `usage`,
`score` are populated on EVERY record unconditionally; only `resolved_input`/`output`/`input_summary`/
`output_summary` are tiered by trace level. The record tree the runner already receives
(`runner.py:232-234`) and currently discards therefore ALREADY carries per-node timing for free. The
runner does not need to retain anything beyond the local `record` it already holds, and **no engine
change and no trace-level change is needed** — the `runner.py:79-81` invariant comment stays true and
must be EXTENDED (not contradicted) to say the record is now read for metrics before being dropped.

**D4. The `stage` label is the node's registry FAMILY, resolved from the BUILT GRAPH — never from the
record's `kind`, never the `node_id`.** Verified: `NodeRegistry.register("<family>")` keys nodes by
family (`registry.py:85-115`) and the search families are exactly seven — `query`, `encode`,
`retrieve`, `fuse`, `rerank`, `postprocess`, `deliver` (confirmed by the seven `register_family` calls
under `shared/libs/pipelines/search/nodes/*/__init__.py`). The record carries only `node_id` + `kind`
(`engine/core.py:177-189`), and `kind` is not globally unique across families, so family must be
resolved by walking the built `Group` and calling `NodeRegistry.family_of(type(node))`
(`registry.py:141-160`). **`node_id` is used only as a map KEY, never as a label** — a stored custom
search blob can name its nodes arbitrarily, so a `node_id` label would be a user-controlled
cardinality leak (the exact risk flagged in the research's Area-1 risks). Unresolvable → the bounded
sentinel `"unknown"`, mirroring `HttpMetricsMiddleware`'s `_UNMATCHED` discipline.

**D5. No new `RUNTIME_CONFIG` variable. No `SEARCH_METRICS_ENABLED`.** Emission always runs, exactly
like `HttpMetricsMiddleware` always feeds its series; `METRICS_ENABLED`
(`app/config/runtime_config.py:215`) keeps gating *exposure* at `/metrics`
(`routers/metrics/router.py:23-41`). Cost is a handful of counter increments plus one O(node-count)
walk of a ~10-node graph — the same cost class as the `__failed_node_reason` walk that already runs on
failures. Consequence: **`docs/configuration.md` is NOT a ripple for this slice** (and the
env-var coherence ratchet stays green because no var is added).

**D6. Candidate counts come from the app-side READ PORT, not from the trace and not from the `debug`
bag.** `CandidateSet` lives inside the retrieve node's output, which is NOT captured at
`TraceLevel.OFF`; the alternative (threading a count through `CandidateSet` → `RankedHits` →
`SearchResult.debug`) would be an artifact + node change with a PIPELINE.md ripple and a visible
response-shape change. `CollectionReadPortImpl.hybrid_search` already computes `len(candidates)` for
its debug log (`read_port.py:104-106`) and is app-side by construction ("the ONLY component in the
search request path that touches the raw data facades", `read_port.py:1-11`). So the port ACCUMULATES
facts into a per-request probe; the runner EMITS. Two responsibilities, two classes, one emission point.

**D7. The probe is NOT added to the shared `CollectionReadPort` protocol.** That protocol is a pure
engine-side contract in `shared_libs`; adding an observability attribute to it would leak an app
concern into the engine. `SearchRunner.run` receives `read_port: CollectionReadPort` and reads the
probe defensively: `getattr(read_port, "probe", None)`. A port implementation without a probe simply
yields no shape metrics (stage latency + outcome counters still emit). State this as an invariant in
the code comment.

**D8. Rerank: emit RANK DISPLACEMENT, not a raw score delta.** A pre/post score delta is not
meaningful as stated: the pre-rerank score is an RRF/DBSF fused rank-derived score and the post-rerank
score is a cross-encoder logit — different scales (this is precisely why `SearchResponse.score_kind`
exists, `routers/search/models.py:220-228`). Displacement (how far the delivered top_k moved relative
to their retrieval rank) is computable at the runner from the probe's recorded retrieval order and
`[hit.chunk_id for hit in result.hits]`, is scale-free, and is the actual question ("is rerank doing
anything?"). A true score delta would require the rerank node to carry pre+post scores in its output
artifact → artifact + node + PIPELINE.md ripple; deliberately deferred (see OPEN DECISIONS #5).

## New files

### 1. `src/docforge/app/backend/libs/metrics/search_collectors.py`

`class SearchMetrics` — static holder, `__new__` raises (python.md static-only pattern), every series
created once at import time on the default registry. Mirrors `DocForgeMetrics`
(`collectors.py:12-58`) exactly. A separate file rather than extending `collectors.py` because that
file is 58 lines and would more than double, past general.md's ~150-line signal; both files put their
series on the same default registry, so `generate_latest()` renders them together with no
`MetricsService` change.

| Series | Type | Labels (bounded) | Fed from |
|---|---|---|---|
| `docforge_search_runs_total` | Counter | `outcome` ∈ `success` / `failed` / `timeout` / `unavailable` (4) | the runner's outcome branch (`runner.py:239-266`) |
| `docforge_search_run_duration_seconds` | Histogram, tuned buckets | none | root `record.duration_ms / 1000` |
| `docforge_search_duration_seconds` | Histogram, tuned buckets | `stage` ∈ the 7 search families + `unknown` (8) | each LEAF record's `duration_ms`, family-resolved per D4 |
| `docforge_search_hits` | Histogram | none | `len(result.hits)` (success only) |
| `docforge_search_candidates` | Histogram | none | probe: summed candidates over all retrieval calls |
| `docforge_search_zero_result_total` | Counter | none | `len(result.hits) == 0` |
| `docforge_search_degraded_total` | Counter | none | `result.debug.get("degraded")` truthy (`deliver/hits/core.py:61-70`) |
| `docforge_search_retrieval_total` | Counter | `axes` ∈ `dense_sparse` / `dense_only` / `sparse_only` / `none` (4) × `filtered` ∈ `true` / `false` (2) = 8 | probe, per retrieval call |
| `docforge_search_rerank_applied_total` | Counter | none | a `rerank`-family leaf executed (from the family map) |
| `docforge_search_rerank_rank_shift` | Histogram | none | mean abs rank displacement of the delivered hits vs their retrieval rank (emitted only when rerank ran) |

Naming: `docforge_search_runs_total`, not `…_requests_total` (the research's working name) — it counts
RUNNER runs, and the router can 4xx before a run ever starts; `docforge_http_requests_total` already
owns the request-level count.

Buckets: an explicit sub-second-oriented ladder (e.g. `.005 .01 .025 .05 .1 .25 .5 1 2.5 5 10`)
rather than `prometheus_client`'s default, because search is sub-second by design and the default
buckets bunch everything into the first two.

**`docforge_search_retrieval_total{axes="none", filtered="true"}` is the concrete reading of
"filter-only vs vector"**: it is exactly the case where `TargetVectorResolver.resolve` raised and the
port returned `[]` after a `logger.warning` (`read_port.py:79-83`) — today an invisible degradation,
about to become a scrapable series. Worth calling out in the file's Code Summary.

### 2. `src/docforge/app/backend/libs/search/probe.py`

`class SearchRetrievalProbe` — `@dataclass(slots=True)`, **zero `prometheus_client` import**, pure
accumulator, one instance per request (per-port, per D6/D7). Fields + one `record_call(...)` method:

- `calls: int` — retrieval calls (>1 under a `ForEach` over sub-queries).
- `candidates_total: int` — summed `len(candidates)`.
- `axes: list[str]` / `filtered: list[bool]` — one entry per call, values from the bounded enum above.
- `retrieval_order: list[str]` — chunk ids in retrieval order, **capped** (e.g. first 200) so memory
  is bounded whatever `candidate_k` a stored blob asks for; used only for D8's displacement.
- `dense_ids` / `sparse_ids: set[str] | None` — filled only by slice 1B, `None` otherwise.

### 3. `src/docforge/app/backend/libs/metrics/search_emitter.py`

`class SearchMetricsEmitter` — static-only (`__new__` raises), the ONLY component that calls
`SearchMetrics`. Small, single-purpose methods (general.md: <30 lines each, numbered steps):

- `family_map(group: Group) -> dict[str, str]` — walks the built graph with the SAME node taxonomy as
  `SearchRunner.__bind_read_port` (`runner.py:134-156`): `Group` → recurse, `ForEach` → recurse into
  `.body`, `ActionNode` → `NodeRegistry.family_of(type(node))`. Missing `ForEach.body` coverage would
  silently label every sub-query node `unknown`, so the taxonomy parity is load-bearing and gets its
  own test.
- `emit(record, result, probe, families, outcome)` — the single public entry: observes the run
  duration, walks `record.children` depth-first observing each LEAF's `duration_ms` under its family
  label (group records are skipped — their duration is a sum and would double-count; the ROOT group's
  duration feeds `…_run_duration_seconds` instead), then the outcome/shape counters, then the probe
  series, then rerank displacement when a `rerank` family ran.
- `_rank_shift(delivered_ids, retrieval_order) -> float | None` — pure, returns `None` when there is
  nothing to compare (empty hits, or no recorded order).

## Modified files

| File | Anchor | Change |
|---|---|---|
| `app/backend/libs/search/read_port.py` | `__init__`, `read_port.py:36-44` | Construct and expose `self.probe = SearchRetrievalProbe()` (per-request scope — consistent with the class's own "constructed per-request; carries no cross-request state" contract, `read_port.py:11`). **`SearchService` is NOT modified**: it already constructs the port per request (`service.py:181`), so the probe rides along for free. |
| `app/backend/libs/search/read_port.py` | early return, `read_port.py:79-83` | Record the `axes="none"` call on the probe before returning `[]` (the filter-only case must be counted, not silently lost). |
| `app/backend/libs/search/read_port.py` | after the facade call, `read_port.py:87-107` | Record one call on the probe: axes derived from whether `dense`/`sparse` are non-empty (the resolver's own output, `read_port.py:80`), `filtered = bool(filters)`, `len(candidates)`, and the capped id order. |
| `app/backend/libs/search/runner.py` | `__init__`, `runner.py:75-84` | Nothing functional; EXTEND the `TraceLevel.OFF` comment (`runner.py:79-81`) so it stays TRUE: the record is now read for structural metrics (duration/kind/score survive OFF) before being discarded — no payload capture is added. (methodology.md DoD #4: a comment the diff makes false must move with it.) |
| `app/backend/libs/search/runner.py` | `run`, `runner.py:220-270` | Hoist `record`/`result`/`outcome` locals before the `try`; set `outcome` on each branch (`timeout` at :247-248, `unavailable` at :250-251, `failed` at :253, `success` at :266); in the `finally`, as its FIRST statement, `try: SearchMetricsEmitter.emit(...) except Exception as exc: self.logger.warning(…)`, then the existing `self._pool.release(...)` untouched. Import the emitter module DIRECTLY (`from ..metrics.search_emitter import SearchMetricsEmitter`), not via `..metrics`'s `__init__`, so the runner never drags `MetricsService` (and its `QueueClient`/`Database` imports) into the search import graph. |

## Ripples — slice 1A

| Coupling-map row | Verdict |
|---|---|
| a request/response model → snapshot + SDK mirror + `parity_map` + MCP + `docs/rest-api.md` | **SKIPPED** — no route, no request field, no response field changes. `/metrics` is `include_in_schema=False` and outside `/api/v1` (`routers/metrics/router.py:23-41`), so it has never been in the snapshot. Still RUN the drift check as verification (expect a zero diff). |
| a node / family / transition / node config → `PIPELINE.md` (+ `ENGINE_BLOB_VERSION`) | **SKIPPED for 1A** — no node, no config, no artifact changes (that is 1B's ripple). |
| a table/column → migration | **SKIPPED** — no schema change anywhere in this plan. |
| an env var / `RUNTIME_CONFIG` → `.env.example` + `docs/configuration.md` | **SKIPPED** — D5: no new var. |
| `compose/**` → `config-check-all` + `compose/README.md` + Makefile | **SKIPPED** — a new series on the default registry renders through the EXISTING `/metrics` path; the telemetry overlay needs no change (`compose/overlays/compose.telemetry.yml` untouched). |
| the frontend → full gate | **SKIPPED** — no frontend file touched. |
| `.claude/**` → `scripts/backup-claude.sh` | **REQUIRED** — see below. |

**Required doc ripples for 1A:**

1. `.claude/rules/architecture.md` — add ONE named invariant to the trace/observability section (which
   already states "Capture de trace (invariant moteur)…"): *metric emission and the extra store
   round-trips that feed it live at the app-side runner/read-port boundary, never in a node; a node may
   forward its config to an injected capability but never emits*. Research explicitly verified this and
   the orchestrator auto-improvement protocol wants it captured so no future agent re-derives it.
   → then run `scripts/backup-claude.sh` (repo is PUBLIC, `.claude/` is never committed; the backup is
   its only persistence).
2. `docs/architecture.md` — VERIFY at implement time whether it carries an observability/metrics
   section; if it does, add the same one-liner. (Not asserted here; it is a top-level tracked doc, so a
   dead backticked path added carelessly would trip `test_tracked_docs_path_references_exist`,
   `tests/units/coherence/test_doc_coherence.py:128-140` — only reference paths that exist.)
3. `services/telemetry/**` Grafana dashboard JSON — OPTIONAL follow-up panels (see OPEN DECISIONS #4).
   Not required for the series to be scrapable.

## Guards — slice 1A (delivered WITH the slice, per methodology.md DoD #2)

New `src/docforge/tests/units/search/test_search_metrics.py` (serviceless; the emitter is a pure
function of a fake built graph + a hand-built `NodeExecutionRecord` tree — no engine run needed):

1. `family_map` covers leaves, nested groups AND `ForEach` bodies — the bind-walk taxonomy parity of D4.
2. Each leaf's `duration_ms` is observed exactly once under its FAMILY label; group records are not observed.
3. **Cardinality-leak repro**: a record whose `node_id` is absent from the family map is labelled
   `unknown`, and no series anywhere carries a `node_id` or a `collection_id` label.
4. `zero_result` / `degraded` / `hits` fire off `result.hits` and `result.debug`.
5. Rerank displacement is emitted only when a `rerank`-family leaf ran, and `_rank_shift` returns
   `None` (no observation) for empty hits / no recorded order.
6. **Emitter-failure containment repro** (the highest-value guard): with the emitter monkeypatched to
   raise, `SearchRunner.run` still raises its ORIGINAL `SearchRunTimeout` / still returns its result,
   and the graph is still released to the pool. This is the D2 invariant as an executable test.

New `src/docforge/tests/units/search/test_search_probe.py`:

7. axes classification for all four cases (dense+sparse, dense-only, sparse-only, none-resolved),
   `filtered` flag, accumulation across multiple `hybrid_search` calls (the `ForEach` case), and the
   `retrieval_order` cap.

Extend `src/docforge/tests/units/api/test_metrics.py` (the existing pattern, `test_metrics.py:1-40`):

8. the `/metrics` exposition lists the `docforge_search_*` metric names even before any search has run
   (schema stability across scrapes — the property `collectors.py:1-6` claims for the gauges).

---

# SLICE 1B — dense-vs-sparse fusion breakdown (OPT-IN, OFF BY DEFAULT)

**User decision on record:** measure the breakdown, accepting the extra Qdrant calls. Verified why
extra calls are unavoidable: retrieval is ONE server-side hybrid call whose branches Qdrant fuses
internally, and every candidate is stamped with the constant `_RETRIEVAL_SOURCE = "hybrid"`
(`read_port.py:29,101`) — there is no per-branch contribution at the DocForge layer. Confirmed
expressible: `Database.search.hybrid_ids` takes `dense` and `sparse` independently, both defaulting to
`None` (`shared/libs/services/db/facades/search_facade.py:40-51`), so a dense-only and a sparse-only
probe query are one keyword away.

## D9 — the knob is a per-collection SEARCH-blob field, not a request flag

`RetrieveHybridConfig.measure_branch_contribution: bool = False`
(`shared/libs/pipelines/search/nodes/retrieve/hybrid/core.py:24-34`, beside the existing `fusion`).

Justification (all four reasons matter):

1. **It is retrieval BEHAVIOUR** — it changes what the store is asked. `fusion` already lives exactly
   there, per-collection, `extra="forbid"` via `NodeConfig` (CLAUDE.md invariant 3 + this task's
   constraint "per-collection behaviour in the blob over env flags where it's search behaviour").
2. **Zero API-surface ripple.** A `SearchRequest` flag would trigger the full chain: OpenAPI snapshot
   regen + `docforge_sdk/docforge_sdk/models/search.py` + `resources/search.py` `_SearchSpecs` +
   `tests/parity_map.py` + `docs/rest-api.md` + the MCP search tool. A blob field triggers none of it.
3. **Cost-amplification safety (multi-tenant).** A request flag lets ANY holder of
   `Capability.SEARCH` triple the Qdrant load on every query against a shared store. A blob field is
   writable only by whoever can write `collection.search` (`Capability.WRITE`) — i.e. an operator
   deliberately diagnosing ONE collection.
4. **`extra="forbid"` fail-fast** at graph build (CLAUDE.md invariant 5): a typo'd field name breaks the
   build loudly instead of being silently ignored.

**No migration, no version bump.** The blob is opaque JSONB. A collection whose stored `collection.search`
predates the field self-heals at read via `SearchBlobNormalizer` (`service.py:110-116`) → the field
takes its `False` default. `ENGINE_BLOB_VERSION` and the golden-blob ratchet cover the **ingest** stock
blob only (`shared/libs/pipelines/ingest/stages/normalizer.py:52`,
`tests/units/stages/test_default_blob_golden.py`); `shared/libs/pipelines/search/normalizer.py` carries
no version stamp (verified). **Still verify at implement time** that no search-blob golden fixture has
appeared since.

## D10 — where the extra round-trips live, and what they cost

Inside `CollectionReadPortImpl.hybrid_search` (app-side, after the authoritative fused call returns),
**never in a node**. The node's only change is forwarding one more config value into the capability
call, byte-for-byte the same pattern as `fusion=config.fusion` (`retrieve/hybrid/core.py:82-88`) — the
node performs no I/O and emits nothing.

- Flag OFF (default): a single `if` guard short-circuits before any extra work. **Exactly one Qdrant
  query, zero behavioural difference, zero added latency.** This is asserted by a test, not asserted in prose.
- Flag ON: two ADDITIONAL `hybrid_ids` calls — dense-only (`sparse=None`) and sparse-only
  (`dense=None`) — with the SAME `conditions`, `limit` and `max_disabled_exclusions` so the pools are
  comparable, issued CONCURRENTLY via `asyncio.gather` after the authoritative call. Wall-clock cost is
  therefore **+1 round-trip, not +2**; Qdrant load is **3× the retrieval queries** for that collection.
  A rejected alternative: fire-and-forget background tasks (unbounded work on the request path, and the
  result must be readable by the runner before the response returns).
- Best-effort: a probe query that raises is caught, logged at warning, and leaves the breakdown
  unrecorded — the authoritative hits are ALREADY in hand at that point, so a probe failure can never
  degrade a search. Asserted by a test.
- The port records `dense_ids` / `sparse_ids` into the probe; `SearchMetricsEmitter` derives, over the
  FUSED pool, the share of candidates present in the dense branch only, the sparse branch only, and
  both. Emission stays in the one place (the runner), so the port keeps zero `prometheus_client` import.

New series in `search_collectors.py`:

| Series | Type | Labels | Meaning |
|---|---|---|---|
| `docforge_search_branch_contribution_ratio` | Histogram | `branch` ∈ `dense_only` / `sparse_only` / `both` (3) | share of the fused pool attributable to that branch |
| `docforge_search_branch_probe_total` | Counter | `outcome` ∈ `ok` / `error` (2) | how often the opt-in probe ran (so its own cost is visible and an always-failing probe is never silent) |

## Modified files — slice 1B

| File | Anchor | Change |
|---|---|---|
| `shared/libs/pipelines/search/nodes/retrieve/hybrid/core.py` | `RetrieveHybridConfig`, :24-34 | Add `measure_branch_contribution: bool = Field(default=False, description=…)`. A description is MANDATORY (a field without one is rejected by test, per architecture.md's design-surface rule). |
| same file | `run`, :82-88 | Forward `measure_branch_contribution=config.measure_branch_contribution` into `self._read_port.hybrid_search(...)`. |
| `shared/libs/pipelines/search/ports.py` (the `CollectionReadPort` protocol, exported from `shared_libs.pipelines.search`) | `hybrid_search`, :33 | Add the keyword with a `False` default so existing implementations/test doubles stay valid. NOTE: this is the engine-side contract — a BEHAVIOUR argument is legitimate here (`fusion` already is); the *probe object* still must NOT be added (D7). |
| `app/backend/libs/search/read_port.py` | `hybrid_search`, :46-107 | Accept the keyword; after step 2, when enabled, run the two concurrent probe queries best-effort and record the id sets on the probe. Extract them into a private `__probe_branches(...)` helper so `hybrid_search` stays under ~30 lines (general.md). |
| `app/backend/libs/metrics/search_emitter.py` | `emit` | Derive + observe the three ratios when the probe carries branch ids; increment `…_branch_probe_total`. |
| `app/backend/libs/metrics/search_collectors.py` | — | The two new series. |
| `src/docforge/PIPELINE.md` | the search/retrieve section (see :468 for the existing retrieve + `TargetVectorResolver` prose) | Document the new config field literally, its default (OFF), what it costs when ON (3× retrieval queries), and that the breakdown surfaces only as Prometheus series (not in the API response). |

## Ripples — slice 1B

| Coupling-map row | Verdict |
|---|---|
| a node config → `PIPELINE.md` same wave | **REQUIRED** (above). `architecture.md` also gets the D10 sentence folded into the 1A invariant edit → `scripts/backup-claude.sh`. |
| `ENGINE_BLOB_VERSION` bump | **SKIPPED with reason** — the constant + golden ratchet are ingest-only; the search normalizer has no version stamp; stored blobs self-heal to the default. Re-verify no search golden fixture exists. |
| a request/response model → snapshot/SDK/MCP/`docs/rest-api.md` | **SKIPPED** — D9 keeps the knob out of the HTTP surface. The node's `config_schema` reaches clients through `/pipelines/search`'s generic `model_json_schema()`-derived dict, whose OpenAPI SHAPE does not change. Verification: run the sdk-parity drift check and expect a ZERO diff — if it diffs, the snapshot regen + SDK mirror become required after all. |
| the frontend → full gate | **SKIPPED with reason** — the field auto-surfaces in `SchemaForm` because node config forms are schema-driven (architecture.md). No component, no literal mirror of a backend default (the brand/frontend rule "never a literal mirror of a backend default" is satisfied by construction). |
| a table/column → migration | **SKIPPED** — blob is JSONB; no schema change. |
| env var → `docs/configuration.md` | **SKIPPED** — no var. |
| `compose/**` | **SKIPPED** — untouched. |

## Guards — slice 1B

New `src/docforge/tests/units/search/test_branch_contribution.py` (serviceless, stubbed facade):

1. **Default costs nothing** (the headline guard): flag OFF ⇒ `hybrid_ids` called EXACTLY ONCE.
2. Flag ON ⇒ three calls; one carries `sparse=None`, one carries `dense=None`, and all three carry the
   same `conditions` / `limit` / `max_disabled_exclusions`.
3. Ratios are computed correctly from stubbed dense/sparse/fused pools (including the degenerate
   empty-fused-pool case → no observation, no ZeroDivisionError).
4. **Probe-failure containment repro**: a probe query raising ⇒ the authoritative hits are returned
   unchanged, no ratio observed, `…_branch_probe_total{outcome="error"}` incremented.
5. `extra="forbid"` still bites: an unknown field in the retrieve config fails the graph build
   (`duplicate`/unknown-field path). Check whether a generic config-forbid test already covers this
   before adding a redundant one.

---

# SLICE 3B — retrieval-quality regression gate (separate, non-blocking workflow)

**Verified starting points.** `tests/rag_eval/metrics.py` is pure (hit@k, recall@k, MRR — no nDCG);
`harness.py` is an `httpx` REST client + `run_eval` loop needing a LIVE stack (`harness.py:181-196`
does a reachability+auth probe, `client_from_env` returns `None` without `DOCFORGE_TOKEN`);
`synthetic.py:110-138` builds a fully deterministic, network-free corpus (6 regulations × 8 questions
= 48 single-clause-evidence queries); `runner.py` is a human-facing CLI that PRINTS a table and
defaults to QASPER. `gate.yml`'s only service-container job is `db-tests` (a single throwaway
`postgres:16`, :64-107) — there is no Qdrant/Redis/BGE/worker anywhere in CI, and there is no
scheduled or `workflow_dispatch` workflow in the repo at all (`.github/workflows/` = `ci.yml`,
`gate.yml`, `release-sdk.yml`).

## D11 — a standalone workflow, NOT a job in `gate.yml`, NOT a required check

`.github/workflows/retrieval-quality.yml`:

- Triggers: `schedule` (weekly cron — see OPEN DECISIONS #1) + `workflow_dispatch` (with inputs
  `papers` and `tolerance` for a manual diagnostic run). **No `pull_request`, no `push`, and it is
  never `needs:`-ed by `ci.yml`, `gate.yml`, `release-sdk.yml` or `release-images.yml`.**
- `permissions: contents: read` (least-privilege floor, mirroring `gate.yml:28-29`). Artifact upload
  needs nothing more; it deliberately does NOT get `pull-requests: write` — it has no PR to comment on.
- `concurrency: { group: retrieval-quality, cancel-in-progress: false }` so two runs never contend for
  the same heavy stack.
- **"Non-blocking" means never a merge gate, NOT always-green.** The comparison step is allowed to FAIL
  the job (red run + scheduled-failure notification = the signal an operator actually notices);
  `continue-on-error: true` would make the job cosmetic and ignored. Because nothing `needs:` this
  workflow and it must not be added to branch protection's required checks, a red run blocks no merge
  and no release. State this in the workflow's header comment (gate.yml's own header-comment style).

## D12 — the stack: `compose/compose.dev-cpu.yml --profile full up -d --build`

- The alternative (`compose.prod-cpu.yml` with published GHCR images, zero build) is fast but measures
  the LAST RELEASED images, not the tree — useless as a tree-regression signal. So: dev-cpu, built from
  the checkout. `--profile full` is mandatory (app/worker/frontend/mcp sit behind it; without it the
  compose rejects `docforge_frontend depends on undefined service docforge_app`). The GPU-only
  `mineru` / `dots_ocr` profiles stay OFF.
- Cost is real (worker's CPU-torch layer + app + frontend build, plus BGE-M3 weight load — the very
  cost that already justifies bge-server's isolated gate job, `gate.yml:148-153`). Acceptable
  *because* it is scheduled/manual and off the PR path. Optional optimisation if wall-clock hurts:
  pre-build `worker`/`app` with `docker/build-push-action` reusing the gate's existing read-only GHA
  cache scopes (`cache-from: type=gha,scope=gate-build-worker`) and then `up -d --no-build`. Not in
  the first cut — keep the workflow simple until the measured runtime justifies the complexity.
- Config: materialise `services/docforge/.env` from the committed `.env.example` exactly like
  `gate.yml:52-56`, then append `AUTH_ENABLED=true` + `AUTH_ROOT_TOKEN=$(openssl rand -hex 32)` and
  export the same value as `DOCFORGE_TOKEN` for the harness. Auth ON deliberately: the eval should
  exercise the real authenticated path, and `client_from_env` requires a token anyway
  (`harness.py:181-196`).
- Readiness: poll `GET /api/v1/capabilities` (the deployment self-description — version, GPU,
  reachable sidecars) until qdrant + bge_server report reachable, with a bounded deadline (~15 min) and
  a clear timeout failure; fall back to `GET /api/v1/health`
  (`app/backend/routers/health/router.py:16`) if `/capabilities` proves unsuitable at implement time.
  A blind `sleep` is not acceptable — a cold BGE load makes it either flaky or wasteful.
- Teardown: `docker compose … down -v` in an `if: always()` step, and `docker compose … logs` uploaded
  as an artifact `if: failure()` so a red scheduled run is debuggable without a re-run.

## D13 — a small helper IS needed (the task's open question, answered: yes)

`runner.py` prints a human table, defaults to QASPER, and has no baseline/exit-code semantics. New
file `src/docforge/tests/rag_eval/gate.py`:

- `class RetrievalQualityGate` + a thin `main(argv)` (argparse) — run as
  `uv run python -m tests.rag_eval.gate --out report.json --baseline tests/rag_eval/baselines/regulatory.json`.
- Loads the DETERMINISTIC corpus only: `load_regulatory_papers(6)` (`synthetic.py:110`). **QASPER is
  never used in CI** — its HuggingFace datasets-server fetch is a network/determinism flake the
  `tests/rag_eval/README.md` already frames as developer-only; it stays a manual `runner.py` diagnostic.
- Runs `run_eval(client, papers, label="gate", corpus="regulatory", min_tokens=None, target_tokens=None,
  ks=(1,3,5,10), search_limit=10, keep_collection=False)` — the PRODUCT DEFAULT chunk config (a gate
  must measure the shipped default, not a tuned one) and `keep_collection=False` so CI leaves nothing
  behind (the harness already purges by `BENCH_PREFIX`, `harness.py:85-92`).
- Writes a machine-readable report: `{corpus, n_queries, papers, ingested, hit_at: {1,3,5,10}, mrr,
  generated_at, git_sha}`.
- `compare(current, baseline, tolerance) -> Verdict` — a **PURE** function (no I/O, no network), which
  is what makes the gate's own arithmetic unit-testable in the fast serviceless suite that slice 3A just
  started collecting. Fails when, for any GATED metric, `current < baseline - tolerance`.
- **Gated metrics: `hit@5`, `hit@10`, `MRR`.** `hit@1` is deliberately NOT gated — on 48 queries a
  single rank-1/rank-2 flip moves it ~0.02 and it is the jitteriest number in the ladder; it is still
  REPORTED.
- **Tolerance: 0.05 absolute**, `--tolerance`-overridable. Rationale: ANN recall jitter + chunk-boundary
  and embedding nondeterminism. It is a starting value to revisit after 2-3 real runs (OPEN DECISIONS #3).
- Two INTEGRITY failures that must not be mistaken for quality results: `ingested < len(papers)` (an
  ingestion/worker failure) and `n_queries != baseline.n_queries` (corpus drift — the baseline must be
  regenerated deliberately). Both fail with a message naming the cause, not a metric.
- `--update-baseline` writes the baseline file locally for a HUMAN to review and commit. **CI never
  passes it** — the whole point is that the baseline moves only through a reviewed commit.

## D14 — where the baseline lives, and the update ritual

`src/docforge/tests/rag_eval/baselines/regulatory.json` — a NEW tracked directory.
**NOT `tests/rag_eval/data/`**: that path is gitignored (`src/docforge/.gitignore:14:
/tests/rag_eval/data/`, verified with `git check-ignore`), so a baseline there would silently never be
committed — the exact failure mode where a gate "never fires".

Ritual, documented in `src/docforge/tests/rag_eval/README.md` and in the workflow header:
a legitimate retrieval change that moves the numbers ⇒ run the gate locally (or download the
scheduled run's report artifact), run with `--update-baseline`, and commit the new baseline **in the
same PR as the change that moved it**, with the before/after numbers in the commit message. A baseline
bump with no accompanying pipeline change is a red flag to be questioned in review.

## New / modified files — slice 3B

**New:**
- `.github/workflows/retrieval-quality.yml`
- `src/docforge/tests/rag_eval/gate.py`
- `src/docforge/tests/rag_eval/baselines/regulatory.json` (numbers filled from the FIRST successful run — they cannot be invented now)
- `src/docforge/tests/rag_eval/test_gate.py` — serviceless unit tests of `compare(...)` + the report shape

**Modified:**
- `src/docforge/tests/rag_eval/README.md` — a "Regression gate" section: what the workflow does, how to
  dispatch it manually, the gated metrics + tolerance, and the baseline-update ritual.
- repo `CLAUDE.md` — one line for the manual local gate run (commands in CLAUDE.md must be
  copy-pasteable; only reference paths that exist, per `test_claude_md_referenced_paths_exist`).

## Ripples — slice 3B

| Coupling-map row | Verdict |
|---|---|
| `.github/workflows/**` → YAML parse + re-read `needs`/`permissions`/`if`; a RELEASE-flow change never ships blind | **REQUIRED (parse + review)**. This is a NEW standalone workflow that no release workflow references, so the release-flow caution (lesson 0.14.5→0.14.6→0.14.46) does not apply — state that explicitly in the report rather than leaving it ambiguous. |
| `compose/**` → `config-check-all` + `compose/README.md` + Makefile | **SKIPPED with reason** — the workflow CONSUMES the existing `compose/compose.dev-cpu.yml` scenario unchanged. If implementation discovers a compose change is needed (e.g. a CI-lean profile), then `make config-check-all` + `compose/README.md` + the Makefile + CLAUDE.md commands ALL become required. |
| a request/response model / a node / a table / an env var | **SKIPPED** — none touched. |
| the frontend | **SKIPPED** — untouched. |
| `.claude/**` | **SKIPPED for 3B** (1A already owns the `architecture.md` edit + backup). |

## Guards — slice 3B

- `src/docforge/tests/rag_eval/test_gate.py` (serviceless, runs in the fast gate thanks to slice 3A):
  a pass verdict at baseline, a pass just inside tolerance, a FAIL just outside it, a FAIL on
  `ingested < papers`, a FAIL on `n_queries` drift, and the report's JSON shape/round-trip.
- The workflow itself is the live guard; its first green run produces the baseline that arms it.

---

# Verification commands to run (report their real output, never "should pass")

```bash
# --- unit suite + lint (slices 1A, 1B, 3A, 3B helper) ---
cd /home/dev-center/projects/docforge/src/docforge
uv run --no-sync python -m pytest tests/units -q
uv run --no-sync python -m pytest tests/units/search tests/units/api/test_metrics.py -q
uv run --no-sync python -m pytest tests/rag_eval -q -m "not live"      # the suite slice 3A newly collects
uv run ruff check . && uv run ruff format --check .

# --- OpenAPI / SDK parity: EXPECT A ZERO DIFF (1B's config field must not reach the HTTP schema) ---
cd /home/dev-center/projects/docforge/src/docforge
set -a; grep -vE '^\s*#|^\s*$' ../../services/docforge/.env.example > /tmp/ci.env; . /tmp/ci.env; set +a
export LOGGING_ENABLE_CONSOLE=false LOGGING_ENABLE_FILE=false
uv run python app/scripts/dump_openapi.py > /tmp/current_openapi.json
cd ../docforge_sdk && uv run python tests/check_schema_drift.py /tmp/current_openapi.json

# --- coherence ratchets (PIPELINE.md kind/doc-path/env-var/CLAUDE.md-path checks) ---
cd /home/dev-center/projects/docforge/src/docforge
uv run --no-sync python -m pytest tests/units/coherence -q

# --- new workflow YAML parses + is wired the way we think ---
cd /home/dev-center/projects/docforge
python -c "import yaml;yaml.safe_load(open('.github/workflows/retrieval-quality.yml'));yaml.safe_load(open('.github/workflows/gate.yml'));print('yaml ok')"
grep -n "retrieval-quality" .github/workflows/ci.yml .github/workflows/gate.yml .github/workflows/release-*.yml || echo "correctly unreferenced by ci/gate/release"

# --- live end-to-end proof of slice 3B (once, before trusting the baseline) ---
docker compose -f compose/compose.dev-cpu.yml --profile full up -d --build
# wait for /api/v1/capabilities to report qdrant + bge_server reachable, then:
cd src/docforge && DOCFORGE_TOKEN=... uv run python -m tests.rag_eval.gate \
    --out /tmp/rq.json --baseline tests/rag_eval/baselines/regulatory.json --update-baseline
docker compose -f compose/compose.dev-cpu.yml --profile full down -v

# --- .claude ripple ---
/home/dev-center/projects/docforge/scripts/backup-claude.sh     # after the architecture.md edit
```

**Deliberately NOT run, with reason (state this in the implementation report, don't leave it silent):**
`make config-check-all` (nothing under `compose/` is modified) · the frontend gate
(lint/tsc/test/build — no frontend file is touched) · any Alembic command (no schema change).

---

# OPEN DECISIONS implementation must respect

1. **Schedule cadence for `retrieval-quality.yml`** — recommended **weekly** (`0 3 * * 1`), because the
   job is heavy (~20 min) and retrieval-affecting changes are not daily. Alternatives: nightly (faster
   feedback, ~7× the CI minutes) or `workflow_dispatch`-only (zero standing cost, but then nothing
   fires on its own and the gate rots). This is a CI-cost/latency trade-off the code cannot settle
   (research OQ5) — **confirm before the workflow is committed.**
2. **Stack source for the workflow** — recommended **dev-cpu with `--build`** (measures the current
   tree; D12). The cheap alternative (prod-cpu + published GHCR images) measures the last RELEASE
   instead. Confirm if CI wall-clock matters more than tree-accuracy.
3. **Baseline numbers + tolerance** — the numbers cannot be invented at plan time; they come from the
   FIRST successful live run and get committed by a human. The 0.05 absolute tolerance and the
   `hit@5`/`hit@10`/`MRR` gate set are starting values to re-evaluate after 2-3 runs. Until the
   baseline is committed the workflow can only report, not gate.
4. **Grafana panels for `docforge_search_*`** — in scope now, or a follow-up? The series are scrapable
   with no dashboard change; adding panels means editing the provisioned dashboard JSON under
   `services/telemetry/` (uid `docforge-overview`, `${DS_PROMETHEUS}` datasource var). **Recommended:
   follow-up**, kept out of this plan's slices.
5. **Rerank: displacement instead of a raw score delta** (D8). The task asked for "rerank score-delta";
   pre/post scores are on incomparable scales (fused RRF/DBSF vs cross-encoder logit), so this plan
   ships rank displacement + a rerank-applied counter. A true score delta needs the rerank node's
   output artifact to carry both scores → node + artifact + `PIPELINE.md` ripple. **Confirm the
   substitution**, or promote the artifact change into slice 1B.
6. **`docs/architecture.md`** — verify at implement time whether it has an observability section that
   should carry the same "emission at the boundary, never in a node" invariant as
   `.claude/rules/architecture.md`, or whether the `.claude` rule alone is the right home.
7. **Axe 2 remains deferred.** If it is later revived, its first decision is still research OQ2
   (aggregate CTR vs a per-query `query_id` threaded onto `SearchResponse`), because that one decides
   whether an impression log must ship WITH or BEFORE the feedback endpoint.
