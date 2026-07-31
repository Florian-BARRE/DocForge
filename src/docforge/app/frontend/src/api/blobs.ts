// ====== Code Summary ======
// Blob download/open helpers. A blob route needs the Bearer header (see http.apiFetchBlob), which a
// plain <a href>/window.open navigation can't carry — so we fetch the bytes authenticated, wrap them
// in an object URL, and either force a download or open them in a new tab (the PDF preview).

import { blobUrl } from "./explorer";
import { apiFetchBlob } from "./http";

/** Fetch a blob (authenticated) and trigger a browser download under `filename`. */
export async function downloadBlob(hash: string, filename: string): Promise<void> {
  const blob = await apiFetchBlob(blobUrl(hash));
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Fetch a blob (authenticated) and open it inline in a new tab (e.g. the canonical PDF). */
export async function openBlobInNewTab(hash: string): Promise<void> {
  const blob = await apiFetchBlob(blobUrl(hash));
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  // The new tab holds its own reference; revoke ours later so the object URL isn't leaked forever.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
