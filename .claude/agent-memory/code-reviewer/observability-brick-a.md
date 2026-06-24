---
name: observability-brick-a
description: Review notes and recurring anti-patterns from the Brique A observability audit (queue/metrics/heartbeat/events + jobs/monitoring routers)
metadata:
  type: project
---

# Observability Brique A — review findings

Brique A = foundation of the resource/job/monitoring chantier. Now split across the three
roots: shared `common_libs/observability/{heartbeat,events}/`, app-only
`backend.libs.observability.queue` (`app/backend/libs/observability/queue/`), worker-only
`libs.observability.metrics` (`worker/libs/observability/metrics/`), plus
`worker/libs/pipeline/worker/heartbeat.py`, routers `jobs/` + `monitoring/`, migration 009.
Briques B/C build on it (SSE streaming = brique C, batches = future).

**Why:** future observability work plugs into these contracts (EventType enum,
WorkerHeartbeat schema, EVENTS_CHANNEL single channel, monitoring discovery panels).
**How to apply:** when reviewing brique B/C, check they reuse these, don't fork them.

## Verified-correct (don't re-flag)

- `ctx["job_try"]` IS populated by arq itself (arq/worker.py line 578) — `ctx.get("job_try", 1)`
  in tasks.py is correct, not a bug. arq increments it per retry attempt.
- arq status strings `deferred|queued|in_progress|complete|not_found` match `JobStatus` enum.
- arq constants `arq:queue` and `arq:in-progress:` match the hardcoded introspector values.
- `WorkerHeartbeat.from_dict` using `cls.__slots__` IS valid on `@dataclass(slots=True)` —
  the dataclass machinery generates `__slots__` as a tuple of field names. Forward-compat filter works.
- pynvml fail-soft: `nvmlInit()` wrapped in `try/except NVMLError` → `_available=False`. Correct.

## Recurring anti-patterns caught (reusable)

- **Misplaced/orphan section comment in bucket `__init__.py`**: the app-only
  `app/backend/libs/observability/__init__.py` had a `# --- Queue introspection ---` header with the
  import 8 lines below it under a different section, and imports not alphabetic/grouped cleanly.
  Cosmetic but violates the labeled-section convention.
- **Hardcoded third-party magic strings instead of importing the library constant**:
  introspector hardcodes `"arq:queue"`/`"arq:in-progress:"` rather than importing
  `arq.constants.default_queue_name` / `in_progress_key_prefix`. Values are correct today but
  drift-prone across arq upgrades. Prefer importing the constant.
