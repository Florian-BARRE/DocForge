---
name: frontend-sse-lifecycle
description: Canonical EventSource lifecycle pattern every DocForge SSE-consuming React component must mirror; what to verify in review
metadata:
  type: reference
---

# Frontend SSE lifecycle — review checkpoint

The reference implementation is `DocumentsTab.tsx` (`components/documents/`). Every other SSE
consumer (e.g. `ObservabilityDashboard.tsx`) must mirror it. When reviewing any component that
opens an `EventSource`, verify all of:

1. **Open ONCE** in a `useEffect` whose deps are only stable `useCallback` fetchers (`[]` deps) —
   so the effect does not re-run and reopen the stream on every render.
2. **`es.close()` in the cleanup** return, plus `clearTimeout(debounceRef)` and
   `clearInterval(pollRef)` (both nulled).
3. **Polling fallback** started by `es.onerror` → `startPolling`, guarded
   (`if (pollRef.current !== null) return`) so onerror can't stack intervals.
4. **Fallback torn down on event resume**: the debounced `scheduleRefetch` (bound to
   `job.updated` + `stage.progress`) must `clearInterval(pollRef)` first — otherwise SSE + polling
   double-fetch forever.
5. **Auth in the URL**: `streamMonitoring` / `streamCollectionDocuments` (in `api/client.ts`) append
   `?token=${encodeURIComponent(_bearerToken)}` because EventSource can't send headers. Confirm the
   stream factory passes it.

Known acceptable deviation: an in-flight `await fetch` resolving after unmount can `setState` on an
unmounted component. The codebase accepts this (no `mounted` guard) — DocumentsTab does the same and
React 18 makes it a harmless no-op. Do not flag as a blocker.
