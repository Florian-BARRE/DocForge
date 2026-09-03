// ====== Code Summary ======
// Small helpers local to the config-snippet export/apply flow — kind labels for the TabNav, the
// `.dfsnippet` filename convention, and the client-side "save this JSON as a file" trigger (the
// snippet body already lives in memory as parsed JSON, fetched via a plain `apiFetch`, unlike the
// whole-collection bundle which streams bytes behind auth — see api/transfers.ts's downloadTransfer).

import type { CollectionSnippet, SnippetKind } from "../../../api/snippets";
import { SNIPPET_FILE_EXTENSION } from "../../../api/snippets";

export const SNIPPET_KIND_LABEL: Record<SnippetKind, string> = {
  pipeline: "Ingestion pipeline",
  search: "Search pipeline",
  schema: "Metadata schema",
};

export function snippetFilename(collectionName: string, kind: SnippetKind): string {
  return `${collectionName}-${kind}${SNIPPET_FILE_EXTENSION}`;
}

/** Serializes a fetched snippet to pretty JSON and triggers a browser download under `filename`. */
export function downloadSnippet(snippet: CollectionSnippet, filename: string): void {
  const blob = new Blob([JSON.stringify(snippet, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
