---
name: chain-failure-policy
description: Uniform chain failure-policy model (CHUNK 2) — gate failure_policy/on_degraded, ChainExhaustedError, max_duration_ms wiring, per-stage defaults, degradation traces, reindex nuance
metadata:
  type: project
---

# Chain failure-policy model (CHUNK 2, 2026-06-25)

Every fallible ingestion chain (parse/enrich/embed) now shares ONE exhaustion contract on the gate.

## ChainGateConfig (`config/pipeline/chain_gate_config.py`)
- Fields: `min_score`, `max_duration_ms`, `failure_policy: Literal["raise","continue"]`,
  `on_degraded: Literal["empty","best_effort"]`. `model_config = ConfigDict(extra="ignore")`
  so old gates (and the removed `max_cost_usd`) still load.

## Chain primitive (`providers/chain/`)
- `core.py::Chain.call` applies the policy on exhaustion via `_on_exhausted`:
  raise → `ChainExhaustedError(stage, attempts)` (RuntimeError subclass, `errors.py`); continue+empty →
  `ChainOutcome(result=None, degraded=True)`; continue+best_effort → highest-scoring SUCCEEDED
  below-threshold result (falls to empty if all hard-errored). Accepted result → `degraded=False`.
- `ChainExhaustedError` msg shape: `'<stage>' chain exhausted: all N provider(s) failed or scored
  below threshold: docling(score=0.30, 120ms), mineru(error=RuntimeError: ..., 5000ms)`.
- `chain_gate.py::should_escalate` now ENFORCES `max_duration_ms` (attempt slower than budget escalates).
- `ChainOutcome.degraded: bool` (models.py); `ChainHelpers.gate_tripped(outcome)` → "error"|"score"|"time"|None.

## Per-stage default gate failure_policy
- parse (`ParseConfig.gate`) = **raise**; embed (`EmbedConfig.gate`) = **raise**.
- enrich classifier_gate/ocr_gate/vlm_gate = **continue** (ocr_gate also keeps `min_score=0.85`).
- NO raise-only restriction — any collection may set any stage to raise OR continue (expert choice).
  A continue parse → empty IR (`S1Helpers.empty_ir`, doc done with 0 blocks); a continue embed batch → no vectors.

## Call-sites (hand-rolled raises DROPPED)
- S1 `s1_parse/core.py`: no more `raise RuntimeError`; chain raises per policy. result=None branch =
  degraded empty IR. `S1Result.markdown_key` now `str | None`.
- S6 `s6_embed_index/embedder.py`: no more `raise RuntimeError`; result=None branch under `continue`
  emits SAME-LENGTH `[None]` placeholders (NEVER drops the batch). Positional contract all_dense[i] <->
  index_chunks[i] is load-bearing (Qdrant upsert aligns by index; `_build_point` skips None). Return type
  `list[list[float] | None]`. embed_values scatters None safely (no IndexError). sparse list back-filled to stay aligned.
- S2 classifier/ocr/vlm: degraded paths (PHOTO/skip/skip) now POLICY-DRIVEN; raise gate → ChainExhaustedError → doc failed.

## Degradation observability
ChainTrace IR (`domain/ir/models/chain_trace.py`) gained `degraded: bool` + `gate_tripped: str | None`.
Stamped by S1Helpers.stamp_parse_trace, S6Embedder, S2 TraceHelpers.from_outcome (all use ChainHelpers.gate_tripped).

## Reindex nuance (`config_repo_helpers.py::reindex_diff`)
`_strip_non_reindex_keys` recursively removes `failure_policy`/`on_degraded` from each non-search
pipeline section BEFORE comparison → policy toggles are NOT reindex-relevant; gate `min_score`/
`max_duration_ms` changes on parse/enrich/embed STILL flag reindex (can change which provider runs).

## CHUNK 3 cleanup (2026-06-25) — DONE
- `ProviderChain` + `_PredicateGate` REMOVED (files `provider_chain.py`/`predicate_gate.py` deleted;
  `chain/__init__` + `providers/__init__` now export `Chain` instead). Were test-only, no live path.
- `provider_call.cost` sentinel REMOVED end-to-end: column gone from `models/provider_call.py`;
  `ProviderCallCache.put` / `CallKeyHelpers.persist` lost the `cost` param; S2 runner return tuples
  shrank `(result, cost, trace, hit)` → `(result, trace, hit)` (cache_runner/vlm_runner/figure_routing).
  **Migration TODO (migration-engineer):** drop column `provider_call.cost` (Float, NOT NULL,
  server_default="0.0"), defined in `001_initial_schema.py:145`. No live migration written yet.
- Empty-chain rule DOCUMENTED in `chain_builders.py` class docstring: REQUIRED (parse/classifier/embed)
  raise ProviderUnavailableError on empty; OPTIONAL (ocr/vlm) return None=disabled. Behavior unchanged.
- Per-family score semantics DOCUMENTED in `ChainGateConfig` docstring: `min_score` means
  block-ratio (parse) / char-confidence (ocr) / structured-validity (vlm) — only comparable within a
  family; OCR's 0.85 default is intentional (real 0-1 confidence metric), do NOT normalize.

## DEFERRED (not CHUNK 2): search/semantic chains (rerank, query_transform, S4 semantic split),
discovery/UI overlay work. Discovery already surfaces ingestion gates → new fields appear via JSON schema.
