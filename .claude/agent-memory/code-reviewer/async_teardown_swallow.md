---
name: async-teardown-swallow
description: Anti-pattern — async worker/task teardown that swallows all exceptions silently, hiding genuine crashes
metadata:
  type: feedback
---

When reviewing async background-task code (worker loops, `asyncio.create_task` + cancel-on-stop
patterns), flag any teardown that catches `Exception` (or `(asyncio.CancelledError, Exception)`)
and `pass`es without logging. Same for last-resort `except Exception` nets inside a `_run` loop
that distribute the error to futures but never log it.

**Why:** In the bge_server batching engine (`src/bge_server/libs/batching/worker.py`), `stop()`
awaited the cancelled task under `except (asyncio.CancelledError, Exception): pass`, and `_run`'s
outer safety net set the exception on every future but logged nothing. A genuine bug in batch
formation or scatter would vanish with zero trace — the worker keeps looping, clients get an
opaque error, and there is no log to debug from. `CancelledError` is the *expected* path and
should pass silently; any other `Exception` is unexpected and must be logged (warning/exception).

**How to apply:** For background-task teardown, require the shape
`except asyncio.CancelledError: pass` separated from `except Exception as exc: self.logger.exception(...)`.
For last-resort nets that fan an error out to futures, require a `self.logger.exception(...)` (or
`.error`) before the fan-out. Low/Medium-severity finding, not a blocker, but it recurs in any
hand-rolled queue+worker design.
