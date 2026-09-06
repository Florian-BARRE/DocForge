// ====== Code Summary ======
// The single state<->URL mapping for the shell's View union. Hash-based (`#/collections/:id/...`)
// because the app is mounted by FastAPI's StaticFiles(html=True), which only serves index.html for
// the root/directory index — not for arbitrary unknown paths (see useUrlSync.ts) — so a path-based
// scheme would 404 on refresh without a backend change. The hash never reaches the server, so it
// needs none. Kept in one file so serialize/parse can't drift apart.

import type { View } from "./view";

// Home is the default landing — the fleet dashboard is the "where do I start" page now that a
// second global-nav destination (All Jobs) exists alongside Collections.
const DEFAULT_VIEW: View = { name: "home" };

/**
 * Serialize a View into a hash path (without the leading '#').
 *
 * @param view - The current shell view.
 * @returns A path string such as "/collections/abc/documents".
 */
export function serializeViewToHash(view: View): string {
  switch (view.name) {
    case "home":
      return "/home";
    case "all-jobs":
      return "/jobs";
    case "monitoring":
      return "/monitoring";
    case "collections":
      if (view.health === "attention") return "/collections/filter/attention";
      if (view.health === "operational") return "/collections/filter/operational";
      return "/collections";
    case "new-collection":
      return "/collections/new";
    case "import-collection":
      return "/collections/import";
    case "collection":
      return `/collections/${encodeURIComponent(view.collectionId)}`;
    case "collection-metadata":
      return `/collections/${encodeURIComponent(view.collectionId)}/metadata`;
    case "collection-edit":
      return `/collections/${encodeURIComponent(view.collectionId)}/edit`;
    case "collection-pipeline":
      return `/collections/${encodeURIComponent(view.collectionId)}/pipeline`;
    case "collection-search-pipeline":
      return `/collections/${encodeURIComponent(view.collectionId)}/search-pipeline`;
    case "collection-jobs":
      return `/collections/${encodeURIComponent(view.collectionId)}/jobs`;
    case "collection-documents":
      return `/collections/${encodeURIComponent(view.collectionId)}/documents`;
    case "collection-search":
      return `/collections/${encodeURIComponent(view.collectionId)}/search`;
    case "document":
      return `/collections/${encodeURIComponent(view.collectionId)}/documents/${encodeURIComponent(view.documentId)}`;
    case "job":
      return `/collections/${encodeURIComponent(view.collectionId)}/jobs/${encodeURIComponent(view.jobId)}`;
    case "workers":
      return "/workers";
    case "api-keys":
      return "/api-keys";
    case "api-key":
      return `/api-keys/${encodeURIComponent(view.keyId)}`;
  }
}

/**
 * Parse a `window.location.hash` value back into a View. Falls back to the collections list for
 * an empty, malformed, or unrecognized path — refresh/back-forward never lands on a dead screen.
 *
 * @param hash - The raw `window.location.hash` (leading '#' optional).
 * @returns The View the hash resolves to.
 */
export function parseViewFromHash(hash: string): View {
  const path = hash.replace(/^#/, "");
  const segments = path.split("/").filter(Boolean).map(decodeURIComponent);

  if (segments.length === 0) return DEFAULT_VIEW;

  const [root, ...rest] = segments;

  if (root === "home") return rest.length === 0 ? { name: "home" } : DEFAULT_VIEW;
  if (root === "jobs") return rest.length === 0 ? { name: "all-jobs" } : DEFAULT_VIEW;
  if (root === "monitoring") return rest.length === 0 ? { name: "monitoring" } : DEFAULT_VIEW;
  if (root === "workers") return rest.length === 0 ? { name: "workers" } : DEFAULT_VIEW;

  if (root === "api-keys") {
    if (rest.length === 0) return { name: "api-keys" };
    if (rest.length === 1) return { name: "api-key", keyId: rest[0] };
    return DEFAULT_VIEW;
  }

  if (root !== "collections") return DEFAULT_VIEW;
  if (rest.length === 0) return { name: "collections" };
  if (rest[0] === "new" && rest.length === 1) return { name: "new-collection" };
  if (rest[0] === "import" && rest.length === 1) return { name: "import-collection" };
  if (rest[0] === "filter" && rest.length === 2) {
    if (rest[1] === "attention") return { name: "collections", health: "attention" };
    if (rest[1] === "operational") return { name: "collections", health: "operational" };
    return { name: "collections" };
  }

  const [collectionId, tab, subId] = rest;
  if (!collectionId) return DEFAULT_VIEW;
  if (!tab) return { name: "collection", collectionId };

  switch (tab) {
    case "metadata":
      return { name: "collection-metadata", collectionId };
    case "edit":
      return { name: "collection-edit", collectionId };
    case "pipeline":
      return { name: "collection-pipeline", collectionId };
    case "search-pipeline":
      return { name: "collection-search-pipeline", collectionId };
    case "jobs":
      return subId
        ? { name: "job", collectionId, jobId: subId }
        : { name: "collection-jobs", collectionId };
    case "documents":
      return subId
        ? { name: "document", collectionId, documentId: subId }
        : { name: "collection-documents", collectionId };
    case "search":
      return { name: "collection-search", collectionId };
    default:
      return { name: "collection", collectionId };
  }
}
