// ====== Code Summary ======
// The app's whole navigation surface as one discriminated union — hand-rolled, in-memory routing
// (no router dependency). Every page receives the current view's params as props and a single
// `onNavigate` callback; App.tsx is the only place that switches on `view.name`.

export type View =
  // `health` is an optional deep-linkable preset (reachable via the URL, e.g. shared links — the
  // sidebar itself no longer has dedicated shortcuts for it, CollectionsToolbar's own health tabs
  // are the single source of truth) — absent (or "empty") means the unfiltered fleet list, matching
  // CollectionsToolbar's own `FleetHealthFilter` values (see features/collections/state/useCollectionsFleet.ts).
  | { name: "collections"; health?: "attention" | "operational" }
  | { name: "new-collection" }
  | { name: "import-collection" }
  | { name: "collection"; collectionId: string }
  | { name: "collection-metadata"; collectionId: string }
  | { name: "collection-edit"; collectionId: string }
  | { name: "collection-pipeline"; collectionId: string }
  | { name: "collection-search-pipeline"; collectionId: string }
  | { name: "collection-jobs"; collectionId: string }
  | { name: "collection-documents"; collectionId: string }
  | { name: "collection-search"; collectionId: string }
  | { name: "document"; collectionId: string; documentId: string }
  | { name: "job"; collectionId: string; jobId: string }
  | { name: "workers" }
  | { name: "api-keys" }
  | { name: "api-key"; keyId: string };

export type Navigate = (view: View) => void;
