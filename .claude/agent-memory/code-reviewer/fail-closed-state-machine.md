---
name: fail-closed-state-machine
description: The ingestion document-status state machine — failed-on-any-error, done-only-on-full-success — and where each transition lives
metadata:
  type: project
---

The worker ingestion path enforces a fail-closed document-status state machine. When reviewing any
change to the orchestrator (`src/docforge/worker/libs/pipeline/orchestrator/`), verify this still holds.

**State machine (where each transition is written):**
- `processing` — set in `s012_runner.py::run_s0` before S0 runs.
- `parsed` — INTERMEDIATE, written by `s012_persist.py::persist_s012` after S0/S1/S2. NOT terminal.
- `done` — TERMINAL success, written ONLY by `core.py::StageEngine.run` via `S012PersistHelpers.mark_done`,
  AFTER `s456.run_s456` returns (i.e. chunks persisted and, when a collection is set, Qdrant upsert done).
- `failed` — written by three guards: `s012_persist.guarded_run` (S0/S1/S2 errors), the `try/except`
  around `persist_s012` in `core.py`, and `s456_runner.run_s456` (S4/S5/S6 errors). All re-raise.

**Why:** a document must never read as `done`/ingested while its chunks or vectors are missing. The
`done` write was deliberately split out of `persist_s012` (which used to write `done` directly) so it
only happens on full success.

**How to apply when reviewing:**
- `mark_failed` (in `s012_persist.py`) wraps its DB write in try/except and logs — so a secondary DB
  failure never masks the original stage error. That swallow is intentional and correct (it logs loudly).
- The None-collection path in `s456_runner._execute_s456` (`if deps.chunk_repo is None: return` and the
  `else:` that persists chunks to Postgres without Qdrant) is a LEGIT skip — must stay distinct from any
  failure flip. A collection set but no S6 stage available is a HARD error (RuntimeError → failed).
- `dry_run` was fully purged (2026-06-25). Any reintroduction of a "preview/no-write" conditional around
  these writes would re-open the door to a stage failure reading as `done`. Reject `if not <flag>:` guards
  wrapping the status/persist writes.
- Test coverage: `tests/units/test_pipeline_fail_closed.py` asserts each leg (failed on S6 fail, clean
  no-collection persist with `statuses == []`, hard error when collection set but S6 missing).
