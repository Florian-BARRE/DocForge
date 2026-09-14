// ====== Code Summary ======
// The single state<->URL mapping for the shell's View union. Hash-based (`#/collections/:id/...`)
// because the app is mounted by FastAPI's StaticFiles(html=True), which only serves index.html for
// the root/directory index — not for arbitrary unknown paths (see useUrlSync.ts) — so a path-based
// scheme would 404 on refresh without a backend change. The hash never reaches the server, so it
// needs none. Kept in one file so serialize/parse can't drift apart.
//
// Deployment-scope routes were reorganized for the IA redesign (2026-09, W1): `/home` -> `/overview`,
// `/jobs` -> `/activity`, `/workers` -> `/fleet`, `/api-keys` -> `/settings`. The OLD hashes are still
// PARSED (back-compat for bookmarks/shared links) but never SERIALIZED — a fresh navigation always
// writes the new path.
//
// Collection-scope routes were realigned for W2 (the rail scope-swap): `metadata` -> `schema`,
// `edit` -> `settings`, `pipeline`/`search-pipeline` -> `pipelines`(`/ingestion`|`/search`), `jobs` ->
// `activity`. Same back-compat rule: old segments still PARSE, never SERIALIZE.

import type { View } from "./view";

// Overview is the default landing — the fleet dashboard is the "where do I start" page.
const DEFAULT_VIEW: View = { name: "overview" };

/**
 * Serialize a View into a hash path (without the leading '#').
 *
 * @param view - The current shell view.
 * @returns A path string such as "/collections/abc/documents".
 */
export function serializeViewToHash(view: View): string {
  switch (view.name) {
    case "overview":
      return "/overview";
    case "activity":
      if (view.tab === "failures") return "/activity/failures";
      if (view.tab === "trends") return "/activity/trends";
      return "/activity";
    case "collections":
      if (view.health === "attention") return "/collections/filter/attention";
      if (view.health === "operational") return "/collections/filter/operational";
      if (view.health === "empty") return "/collections/filter/empty";
      return "/collections";
    case "new-collection":
      return "/collections/new";
    case "import-collection":
      return "/collections/import";
    case "collection":
      return `/collections/${encodeURIComponent(view.collectionId)}`;
    case "collection-documents":
      return `/collections/${encodeURIComponent(view.collectionId)}/documents`;
    case "collection-search":
      return `/collections/${encodeURIComponent(view.collectionId)}/search`;
    case "collection-pipelines":
      return `/collections/${encodeURIComponent(view.collectionId)}/pipelines/${view.stage === "search" ? "search" : "ingestion"}`;
    case "collection-schema":
      return `/collections/${encodeURIComponent(view.collectionId)}/schema`;
    case "collection-activity":
      return `/collections/${encodeURIComponent(view.collectionId)}/activity`;
    case "collection-settings":
      return `/collections/${encodeURIComponent(view.collectionId)}/settings`;
    case "document":
      return `/collections/${encodeURIComponent(view.collectionId)}/documents/${encodeURIComponent(view.documentId)}`;
    case "job":
      return `/collections/${encodeURIComponent(view.collectionId)}/jobs/${encodeURIComponent(view.jobId)}`;
    case "fleet":
      return "/fleet";
    case "settings":
      if (view.section === "audit") return "/settings/audit";
      if (view.section === "deployment") return "/settings/deployment";
      return "/settings";
    case "api-key":
      return `/settings/keys/${encodeURIComponent(view.keyId)}`;
  }
}

/**
 * Parse a `window.location.hash` value back into a View. Falls back to Overview for an empty,
 * malformed, or unrecognized path — refresh/back-forward never lands on a dead screen. Also resolves
 * the pre-redesign hashes (`/home`, `/jobs`, `/workers`, `/api-keys[/:id]`) to their new destinations.
 *
 * @param hash - The raw `window.location.hash` (leading '#' optional).
 * @returns The View the hash resolves to.
 */
export function parseViewFromHash(hash: string): View {
  const path = hash.replace(/^#/, "");
  const segments = path.split("/").filter(Boolean).map(decodeURIComponent);

  if (segments.length === 0) return DEFAULT_VIEW;

  const [root, ...rest] = segments;

  // Back-compat: pre-redesign roots resolve to their new scope, old hashes never dead-end.
  if (root === "home" || root === "overview") return rest.length === 0 ? { name: "overview" } : DEFAULT_VIEW;
  if (root === "jobs" || root === "activity") {
    if (rest[0] === "failures") return { name: "activity", tab: "failures" };
    if (rest[0] === "trends") return { name: "activity", tab: "trends" };
    return { name: "activity" };
  }
  if (root === "workers" || root === "fleet") return rest.length === 0 ? { name: "fleet" } : DEFAULT_VIEW;

  if (root === "api-keys") {
    if (rest.length === 0) return { name: "settings" };
    if (rest.length === 1) return { name: "api-key", keyId: rest[0] };
    return DEFAULT_VIEW;
  }

  if (root === "settings") {
    if (rest.length === 0) return { name: "settings" };
    if (rest[0] === "keys" && rest.length === 2) return { name: "api-key", keyId: rest[1] };
    if (rest[0] === "audit" && rest.length === 1) return { name: "settings", section: "audit" };
    if (rest[0] === "deployment" && rest.length === 1) return { name: "settings", section: "deployment" };
    return { name: "settings" };
  }

  if (root !== "collections") return DEFAULT_VIEW;
  if (rest.length === 0) return { name: "collections" };
  if (rest[0] === "new" && rest.length === 1) return { name: "new-collection" };
  if (rest[0] === "import" && rest.length === 1) return { name: "import-collection" };
  if (rest[0] === "filter" && rest.length === 2) {
    if (rest[1] === "attention") return { name: "collections", health: "attention" };
    if (rest[1] === "operational") return { name: "collections", health: "operational" };
    if (rest[1] === "empty") return { name: "collections", health: "empty" };
    return { name: "collections" };
  }

  const [collectionId, tab, subId] = rest;
  if (!collectionId) return DEFAULT_VIEW;
  if (!tab) return { name: "collection", collectionId };

  switch (tab) {
    // Back-compat: pre-W2 segments resolve to their realigned destination.
    case "metadata":
    case "schema":
      return { name: "collection-schema", collectionId };
    case "edit":
    case "settings":
      return { name: "collection-settings", collectionId };
    case "pipeline":
      return { name: "collection-pipelines", collectionId, stage: "ingestion" };
    case "search-pipeline":
      return { name: "collection-pipelines", collectionId, stage: "search" };
    case "pipelines":
      return { name: "collection-pipelines", collectionId, stage: subId === "search" ? "search" : "ingestion" };
    case "jobs":
    case "activity":
      return subId
        ? { name: "job", collectionId, jobId: subId }
        : { name: "collection-activity", collectionId };
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
