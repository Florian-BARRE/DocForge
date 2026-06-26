---
name: stale-scoped-tab-bypasses-gate
description: Per-collection sub-tab state survives a collection switch and bypasses the permission gate that only HIDES the tab (AppShell/ContextBar)
metadata:
  type: feedback
---

When a collection-scoped sub-tab (e.g. `activeTab === 'access'`) is gated only by
*hiding the tab button* (ContextBar builds `tabs` from `isCollectionAdmin`), the gate
is bypassable: switching the active collection (`handleSelectCollection`) updates
`activeCollectionId` but does NOT reset `activeTab`. A user who was admin on collection
A and selected the Access tab, then switches to collection B where they are not admin,
keeps `activeTab === 'access'` — the tab button disappears but `renderBody()` still
renders `<CollectionAccessPanel collectionId={B} />` because its branch has no
`isCollectionAdmin` re-check.

**Why:** hiding a control is not the same as gating the route that renders it. The
permission flag is recomputed for the new collection, but the body switch reads only
the persisted tab key. Backend `require_collection_role(admin)` still blocks the API
(403, no data leak), but the UI renders an admin panel to a non-admin.

**How to apply:** when reviewing a shell that threads a derived permission flag down to
gate a tab, check BOTH (a) the tab is hidden when the flag is false AND (b) the body/route
that renders the gated panel re-checks the same flag, OR the scoped tab state is reset on
context (collection) switch. Flag `if (activeTab === 'gated') return <Panel/>` branches
that lack the permission re-check. Related: [[sse-broadcaster-patterns]].
