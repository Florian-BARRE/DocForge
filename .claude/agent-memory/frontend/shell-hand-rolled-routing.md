---
name: shell-hand-rolled-routing
description: The app shell's navigation pattern — a discriminated View union + useState, no router dependency
metadata:
  type: project
---

The app shell (`src/App.tsx`, `src/shell/view.ts`, `src/shell/TopBar.tsx`) routes with a plain
`useState<View>` in `App.tsx` — `View` is a discriminated union (`{ name: "collections" }`,
`{ name: "collection"; collectionId: string }`, etc.) defined in `src/shell/view.ts`. `App.tsx` is
the ONLY place that switches on `view.name`; every page component receives `onNavigate: Navigate`
(`= (view: View) => void`) as a prop and calls it directly — no context, no prop drilling beyond
one level, since `App.tsx` renders each top-level page directly from the switch.

**Why:** the task explicitly forbade adding a router dependency; view-state was judged sufficient
for this app's depth (Collections → detail → pipeline studio / jobs → job detail, plus a
fleet-wide Workers view).

**How to apply:** when adding a new page/view, add one variant to the `View` union in
`src/shell/view.ts`, one branch in `App.tsx`'s render switch, and thread `onNavigate` down to any
child that needs to navigate. `BackLink` (`src/components/BackLink.tsx`) is the shared "← back"
affordance used by every page nested under Collections.
