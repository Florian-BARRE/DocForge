---
name: perf-hardening-step2
description: Step 2 perf pass (2026-07-29) — cgroup-aware torch thread cap, lifespan warmup, gzip responses, model-revision pin (blocked). What shipped and why.
metadata:
  type: project
---

Implemented against an approved audit brief (measured 2x CPU thread oversubscription: `os.cpu_count()`
returned 8 inside a container capped to 4 CPUs via compose `deploy.resources.limits.cpus: "4"`).

**1. Cgroup-aware thread budget — `libs/bge_models/cpu_budget.py` (new file, `CpuBudgetResolver` +
`ResolvedCpuBudget`)**. Static-only helper (same idiom as `DeviceResolver`/`ResolvedDevice` in
`device.py`): reads `/sys/fs/cgroup/cpu.max` (`"<quota> <period>"`), returns
`floor(quota/period)` clamped to >=1, source="cgroup"; falls back to
`len(os.sched_getaffinity(0))` (or `os.cpu_count()`), source="affinity", on ANY failure — missing
file, `"max"` (unlimited), cgroup v1 layout, zero period, garbled content, non-Linux. NEVER raises.
The cgroup path is an injectable parameter (not hardcoded) so tests write a real tmp_path file
instead of mocking pathlib — 8 test cases in `tests/unit/test_cpu_budget.py`.
Wired into `libs/bge_models/service.py::load()` step 3: the `BGE_TORCH_NUM_THREADS=0` auto path now
calls `CpuBudgetResolver.resolve()` instead of raw `os.cpu_count()`; an explicit non-zero
`BGE_TORCH_NUM_THREADS` still wins unchanged. **Verified in prod-shaped compose (4-CPU limit)**:
resolved thread count went from 8 -> 4, log line
`torch intra-op threads set to 4 (BGE_TORCH_NUM_THREADS=0, max_concurrency=1, cpu_budget=4, source=cgroup)`.
`/embed` batch=32 p50 measured ~4759ms post-fix vs the audit's 5294ms baseline (~10% faster,
localhost benchmark — real gain is likely larger under concurrent load where thread thrash compounds).

**2. Lifespan warmup — `backend/lifespan.py`**. New step 5 (TOTAL_STEPS 3->4) between "start batching
engine" and "service ready": calls `CONTEXT.bge_models.encode_dense/.encode_sparse/
.compute_rerank_scores_flat` directly on a single `"warmup"` string/pair — bypasses the batching
engine/HTTP entirely (no queue/lock overhead needed just to prime lazy allocations). Wrapped in one
broad `try/except`, logs at WARNING on failure, never blocks/aborts startup.

**3. Gzip responses — `backend/app.py`**. `app.add_middleware(GZipMiddleware, minimum_size=1024)`
(FastAPI's re-export of Starlette's). No API-shape change — pure `Content-Encoding` negotiation.
Verified: a 32-item `/embed` batch went from 695178 bytes uncompressed to 301726 bytes on the wire
(~2.3x) with `content-encoding: gzip` present when the client sends `Accept-Encoding: gzip`.

**4. Model revision pin — NOT implemented, confirmed infeasible.** See
[[flagembedding-m3-internals]] for the full trace: `revision=` passed to `BGEM3FlagModel`/
`FlagReranker` is a dead kwarg (swallowed by `**kwargs` -> `setattr`, never reaches
`from_pretrained`). Do not attempt this again without first re-verifying against whatever
FlagEmbedding version is pinned in `pyproject.toml` at the time — if a future FlagEmbedding upgrade
starts forwarding kwargs to `from_pretrained`, this could become viable. The alternative (pre-populate
the HF cache via `huggingface_hub.snapshot_download(repo_id, revision=sha)` before model construction)
was scoped but not built — orchestrator/user must decide if that extra complexity is worth it.

Full verification tail (2026-07-29): `ruff check` clean, `mypy` clean (30 files), `pytest -q` 17
passed (9 pre-existing + 8 new cgroup tests). Image rebuild was fast (~4s, only the code layer
changed — dependency layer cached). Container reached `healthy` on first boot, no cold re-pull was
triggered (no revision pin was added, so nothing changed on the HF-download path).
