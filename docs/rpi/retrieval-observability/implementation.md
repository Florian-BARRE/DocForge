# Retrieval observability — Implementation notes

Implements `plan.md` slices **3A + 1A + 1B + 3B** (Axe 2 feedback DEFERRED). On main-tree, **UNCOMMITTED** pending review sign-off.

## Shipped

**3A — rag_eval collected in CI.** `.github/workflows/gate.yml` gained a serviceless step `pytest tests/rag_eval -m "not live"` (the pure metrics + `compare()` units), keeping the live CLI runner out of the fast gate.

**1A — per-search telemetry (`docforge_search_*`).** Emitted at the app-side boundary only (node purity held):
- `search_collectors.py` (SearchMetrics holder), `search_emitter.py` (SearchMetricsEmitter, family_map, pure `_rank_shift`), `search/probe.py` (SearchRetrievalProbe, per-request).
- `SearchRunner.run` emits as the first `finally` statement, wrapped in its own try/except (a raising emit can't mask the real run error nor skip `_pool.release`). `TraceLevel.OFF` kept (duration/kind/score survive).
- Series: runs_total{outcome}, run_duration, duration{stage=registry family}, hits, candidates, zero_result_total, degraded_total, retrieval_total{axes,filtered}, rerank_applied_total, rerank_rank_shift (RANK displacement, not score delta).

**1B — dense/sparse fusion breakdown, opt-in.** Knob `RetrieveHybridConfig.measure_branch_contribution: bool = False` (blob, extra="forbid"). Branch probes live in `CollectionReadPortImpl.hybrid_search` (best-effort, `asyncio.gather` dense-only/sparse-only after the authoritative call; OFF ⇒ exactly one Qdrant query). Series: branch_contribution_ratio{branch}, branch_probe_total{outcome}.

**3B — retrieval-quality regression gate (manual, non-blocking).** `.github/workflows/retrieval-quality.yml`: `workflow_dispatch`-only, `permissions: contents: read`, never `needs:`-ed, no `continue-on-error` (goes red on regression), teardown `if: always()`. Builds dev-cpu `--build`, AUTH_ENABLED + generated token, readiness via `/capabilities`, deterministic `synthetic regulatory` corpus. `tests/rag_eval/gate.py` (pure `compare()`, CLI `--update-baseline`) gates hit@5/hit@10/MRR at 0.05 absolute; hit@1 reported-not-gated; integrity checks. Baseline `tests/rag_eval/baselines/regulatory.json` (tracked, NOT gitignored data/; all-zero placeholder — SEED from the first live dispatch).

## Ripples
Done: PIPELINE.md (1B knob), .claude/rules/architecture.md (telemetry-at-the-boundary invariant) + backup, tests/rag_eval/README.md (Regression gate section), CLAUDE.md (gate command). Skipped-with-reason: SDK/MCP/rest-api (no HTTP change — drift verified zero), migrations (blob is JSONB), docs/configuration.md (no new env var), frontend (schema-driven form auto-surfaces the knob), ENGINE_BLOB_VERSION (golden ratchet is ingest-only; search blob unstamped).

## Verification (real outputs)
- units + rag_eval (serviceless): **1977 passed, 1 skipped, 1 deselected**
- ruff check + format: clean (953 files)
- SDK drift/parity: **645 passed** (zero diff)
- code-reviewer: **APPROVED WITH SUGGESTIONS** (1 LOW: print() in gate.py CLI — accepted-with-precedent)

## Follow-ups (not in scope)
- Seed the baseline from the first live `retrieval-quality` dispatch, commit deliberately.
- Grafana panels for the new `docforge_search_*` series (dashboard addition).
- Axe 2 (feedback / online nDCG-MRR-CTR) — deferred, its design fork (query_id joinability + PII) unresolved.
