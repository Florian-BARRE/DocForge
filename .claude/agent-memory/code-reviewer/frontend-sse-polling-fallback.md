---
name: frontend-sse-polling-fallback
description: DocForge frontend SSE-with-polling-fallback anti-pattern — onerror starts polling that is never stopped after EventSource auto-reconnects, causing permanent double-fetch
metadata:
  type: feedback
---

In DocForge React components that consume an SSE stream with a polling fallback
(pattern introduced in `frontend/src/components/documents/DocumentsTab.tsx`, brique C),
check that the polling fallback is STOPPED once the stream recovers.

**Why:** `EventSource.onerror = startPolling` begins a 2s `setInterval`, but EventSource
auto-reconnects natively. Nothing clears the interval until unmount, so after a single transient
error the component runs BOTH the SSE-driven refetch AND the 2s poll for the rest of its life —
redundant fetches. Correct (not a bug), but wasteful and easy to miss. Caught in the brique C
review (2026-06-23).

**How to apply:** When you see `onerror`/`onError` starting a polling interval, look for a place
that clears it on the next successful event (e.g. inside the debounced refetch / first message
handler). If absent, flag as a SUGGESTION with a one-line fix: clear `pollRef` when an event arrives.

Related: [[sse-broadcaster-patterns]].
