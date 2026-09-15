// ====== Code Summary ======
// The app's whole navigation surface as one discriminated union — hand-rolled, in-memory routing
// (no router dependency). Every page receives the current view's params as props and a single
// `onNavigate` callback; App.tsx is the only place that switches on `view.name`.

export type View =
  // The deployment scope's default landing page — a fleet-wide "step back and manage" dashboard
  // (collections health breakdown, worker/queue summary, recent failures). Rendered by
  // features/home/HomePage.tsx — kept as-is this wave (IA redesign W1 is nav+routing only; the
  // "Home" feature folder itself is a Wave 3 consolidation target, not renamed here).
  | { name: "overview" }
  // `health` is an optional deep-linkable preset, kept in sync BOTH ways with CollectionsToolbar's own
  // `FleetHealthFilter` (see features/collections/state/useCollectionsFleet.ts) — a real route, not
  // just a one-way deep link. Absent means the unfiltered fleet list ("all").
  | { name: "collections"; health?: "attention" | "operational" | "empty" }
  | { name: "new-collection" }
  | { name: "import-collection" }
  | { name: "collection"; collectionId: string }
  | { name: "collection-documents"; collectionId: string }
  | { name: "collection-search"; collectionId: string }
  // `stage` picks which of the two editors is showing; absent means "ingestion" (the default
  // landing sub-tab). Replaces the former separate `collection-pipeline`/`collection-search-pipeline`
  // views — Pipelines is now ONE section with Ingestion|Search as equal-depth English sub-tabs.
  | { name: "collection-pipelines"; collectionId: string; stage?: "ingestion" | "search" }
  // Promoted out of the former Documents-sub-tab "Metadata" into its own top-level tab.
  | { name: "collection-schema"; collectionId: string }
  // This collection's own job history — replaces `collection-jobs` (renamed to match the sidebar's
  // "Activity" label, mirroring the deployment-scope Activity section).
  | { name: "collection-activity"; collectionId: string }
  // Replaces the standalone `collection-edit` view — the contract editor (+ its Danger Zone) and the
  // Transfer (export/import/snippets) panel now render together, in-shell, under Settings.
  | { name: "collection-settings"; collectionId: string }
  | { name: "document"; collectionId: string; documentId: string }
  | { name: "job"; collectionId: string; jobId: string }
  // Deployment scope's fleet-wide job management ("step back and manage") — one observability home
  // split into Jobs (the triage list) / Failures (breakdown + forensics) / Trends (sparklines +
  // backlog). `tab` absent means "jobs" (the default landing sub-tab), same convention as
  // `collection-pipelines`'s `stage`.
  | { name: "activity"; tab?: "jobs" | "failures" | "trends" }
  // Deployment scope's worker/queue/capacity management (was "workers").
  | { name: "fleet" }
  // Deployment scope's admin surface — Keys | Audit | Deployment sub-nav (mirrors `activity`'s
  // `tab` convention). `section` absent means "keys" (the default landing sub-tab).
  | { name: "settings"; section?: "keys" | "audit" | "deployment" }
  | { name: "api-key"; keyId: string };

export type Navigate = (view: View) => void;
