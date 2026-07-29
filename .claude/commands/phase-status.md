---
name: phase-status
description: Show DocForge current implementation status (graph engine stages + suite state)
user-invocable: true
allowed-tools: "Read(*), Bash(*)"
---

# Status

Report the current state of the DocForge (rework) product. There are no legacy "phases" anymore —
the engine is a graph of the 7 ingestion stages plus feature work tracked in the task list.

## Steps

1. **Pipeline stages** — read `src/docforge-rework/PIPELINE.md` (the living reference) and summarize
   the 7 stages and their wired nodes:
   `INTAKE → PARSE → ENRICH → CHUNK → CONTEXTUALIZE → METAGEN → EMBED`.

2. **Engine invariants** — spot-check the three roots exist and are non-empty:
   - [ ] `src/docforge-rework/shared/libs/pipelines/` (the pure engine: base/ engine/ edit/ validation/)
   - [ ] `src/docforge-rework/shared/libs/services/db/` (the `Database` façade)
   - [ ] `src/docforge-rework/app/backend/routers/` (pipelines · collections · documents · explorer · jobs · blobs · search · auth)
   - [ ] `src/docforge-rework/worker/backend/libs/` (runner + persistence)

3. **Test suite state**:
   ```bash
   cd src/docforge-rework && uv run pytest tests/units -q --tb=no | tail -3
   ```

4. **Recent work** — `git log --oneline -15` on the active branch.

5. **Open debt / features** — list the pending items from the task list (TaskList) and any
   `[V1.1]`/`[FEATURE]` markers.

6. **Output a clean summary**: stages implemented, suite pass/fail count, and the open items.
