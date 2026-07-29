---
name: feature-slice-isolation
description: features/<name>/ modules never import from another feature slice, even for tiny pure helpers
metadata:
  type: feedback
---

`src/features/<feature>/` slices do not cross-import each other, even for small pure helper functions (e.g.
`features/collections/relativeTime.ts` humanize-ago helper). When a second feature needs the same shape of helper,
duplicate a small LOCAL copy inside that feature's own directory rather than importing across the boundary.

**Why:** explicit instruction from a task brief (auth feature needed relative-time formatting; told to add a local
`features/auth/relativeTime.ts` instead of importing `features/collections/relativeTime.ts`), consistent with this
codebase's feature-slice architecture — slices should stay independently movable/deletable.

**How to apply:** whenever a feature needs something that already exists in a sibling feature's directory, copy/
adapt a small local version instead of importing it. Shared logic that isn't feature-specific belongs in
`src/components/` or `src/api/` instead (see [[ui-primitives]]), not cross-imported from another feature.
