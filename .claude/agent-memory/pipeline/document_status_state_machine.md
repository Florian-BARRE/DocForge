---
name: document-status-state-machine
description: Document.status lifecycle across S0-S6 + who writes it; the fail-closed guarantee (parsed vs done)
metadata:
  type: project
---

The `document.status` column is written at exactly these points in the (single) live path:

- **S0 start** -> `processing` (`s012_runner.run_s0`, before the guarded run).
- **Any S0/S1/S2 failure** -> `failed` (`S012PersistHelpers.guarded_run`).
- **After S0-S2 + block persist** -> `parsed` (intermediate; `S012PersistHelpers.persist_s012`).
  This used to write `done` directly — that was the silent-success bug (doc read "done" with an
  empty Qdrant when S6 failed, because persist_s012 runs BEFORE S4/S5/S6).
- **Any S4/S5/S6 failure** -> `failed` (`S456Runner.run_s456` guard -> `S012PersistHelpers.mark_failed`).
- **Terminal success (after S456 returns)** -> `done` (`StageEngine.run` step 6 -> `mark_done`).

**Guarantee:** `done` is reached ONLY after S4 chunks AND (when collection_id is set) the S6 Qdrant
upsert succeeded. `parsed` means "IR persisted, indexing not yet confirmed" — a doc stuck there
(e.g. worker crash before mark_done) reads as still-processing, never as ingested.

**API surface:** `DocumentResponse.normalize_status` maps `processing`/`parsed` -> `running`,
`failed` -> `error`. The `indexed` flag (documents/router.py) derives from
`stage_summary.s6 == "done" OR embed_chain_traces present` — S4/S5/S6 are NOT node-cached so the
embed traces are the reliable "S6 indexed this doc" marker.

**Job vs document:** the arq task (`worker/.../worker/tasks.py`) updates only the JOB row on
failure; the DOCUMENT failed-flip is owned by the engine/runners (above), NOT the task.

**`dry_run` is GONE (2026-06-25):** the playground/preview feature was removed long ago; the
`dry_run` param + every `if dry_run` branch were purged from StageEngine.run, the s012/s456
runners, cache_io, s012_persist, result, and tasks.py (~88 occurrences / 8 files). The pipeline
now has ONE path: S4/S5/S6 always run; any stage error always `mark_failed`+raise; `mark_done`
always on success. No no-write/preview mode exists. Do not reintroduce it. The fail-closed guards
(guarded_run, run_s456, persist_s012) are now unconditional, not gated on `not dry_run`.

**Do not** move the `done` write back into persist_s012. **Do not** weaken the NodeCache: a failed
stage is only ever `failed`/absent in stage_run, never cached as a `done` hit (the cache `get`
returns a ref only when `status == "done" and output_ref`).

Related: [[provider-raise-on-failure]]
