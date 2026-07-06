# Test Agent Memory — docforge-rework

- [Bootstrap mechanics](bootstrap-mechanics.md) — shared_libs alias + worker/backend/libs path done once in tests/conftest.py; app booted lazily per-fixture; no worker-root collision
- [NodeRegistry global state](noderegistry-global-state.md) — process-global registry; every test-local fake node needs a session-unique KIND string
- [App boot is slow cold, DB clients are lazy](app-boot-cold-import-cost.md) — ~30s first import (OneDrive-backed tree); PostgresClient logs "connected" but only configures the pool
- [Stage combinatorics test strategy](stage-combinatorics-strategy.md) — bypass StageCompiler cascade via PipelineState.model_copy(update=...) to reach all 32 raw toggle vectors directly
- [Port scratchpad gap plan](port-scratchpad-gap-plan.md) — verified 2026-07-05: every scratchpad script still matches current source 1:1; exact file list + gotchas (dedup, RunBundle, VectorNames, cascade tests) for the still-unwritten tests/units/{nodes,worker,stages/test_view_reader,api}/ + tests/live/
- [Scratchpad port complete](scratchpad-port-complete.md) — DONE 2026-07-05: 357 units + 17 live (5 xfail) green; the one real bug found is an unprovisioned S3 bucket on the live stack (infra follow-up, not fixed here)
