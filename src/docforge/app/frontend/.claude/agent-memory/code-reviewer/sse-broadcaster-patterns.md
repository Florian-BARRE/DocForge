---
name: sse-broadcaster-patterns
description: Recurring review points for DocForge SSE fan-out (EventBroadcaster) and SSE routes — set-iteration safety, silent Redis-drop, the justified no-response_model exception
metadata:
  type: feedback
---

When reviewing DocForge real-time/SSE code (brique C: `libs/observability/events/broadcaster.py`,
`backend/libs/utils/sse.py`, the two `/stream` routes), check these specific points.

**Why:** These are latent or silent-failure patterns that pass tests and tsc but bite later. Caught during the brique C review (2026-06-23).

**How to apply:**

1. **Fan-out over a mutable subscriber set.** `EventBroadcaster.__fan_out` iterates `self._subscribers`
   (a `set`) while `subscribe()`/`unsubscribe()` mutate it. Safe ONLY because the loop contains no
   `await` (atomic on one event loop). Flag any future edit that adds an `await` inside the loop
   (e.g. switching `put_nowait` → `await put` for real back-pressure) — it would raise
   "Set changed size during iteration". Recommend `for q in tuple(self._subscribers):` as cheap insurance.

2. **Silent backend→Redis drop.** The `_run` listen loop (`async for message in self._pubsub.listen()`)
   has no try/except. A Redis restart kills the fan-out task; SSE clients go silent with no log.
   The frontend `onerror` polling fallback does NOT trigger because the browser→backend HTTP stream
   stays open — only the backend→Redis link broke. Always ask for a log + ideally resubscribe-with-backoff.

3. **No-`response_model` on SSE routes is an ACCEPTED, documented exception.** A live `EventSourceResponse`
   stream cannot be described by a Pydantic model. This is fine PROVIDED there's a NOTE comment
   explaining it and `@auto_handle_errors` is still present. Do not flag it as a rule violation.

4. **Route ordering:** the collection-scoped `/stream` must be declared BEFORE the dynamic
   `/{document_id}` route, else "stream" is captured as a document id. Verify physical ordering in the file.

5. **Shutdown ordering:** broadcaster (own Redis connection) must `stop()` BEFORE `arq_pool.close()`
   in lifespan `finally`, with a `hasattr(CONTEXT, "event_broadcaster")` guard.

Related: [[frontend-sse-polling-fallback]].
