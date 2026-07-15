// ====== Code Summary ======
// The app's whole navigation surface as one discriminated union — hand-rolled, in-memory routing
// (no router dependency). Every page receives the current view's params as props and a single
// `onNavigate` callback; App.tsx is the only place that switches on `view.name`.

export type View =
  | { name: "collections" }
  | { name: "new-collection" }
  | { name: "collection"; collectionId: string }
  | { name: "collection-edit"; collectionId: string }
  | { name: "collection-pipeline"; collectionId: string }
  | { name: "collection-search-pipeline"; collectionId: string }
  | { name: "collection-jobs"; collectionId: string }
  | { name: "collection-documents"; collectionId: string }
  | { name: "collection-search"; collectionId: string }
  | { name: "document"; collectionId: string; documentId: string }
  | { name: "job"; collectionId: string; jobId: string }
  | { name: "workers" };

export type Navigate = (view: View) => void;
