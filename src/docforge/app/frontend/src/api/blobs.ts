// ====== Code Summary ======
// Blob download/open helpers. A blob route needs the Bearer header (see http.apiFetchBlob), which a
// plain <a href>/window.open navigation can't carry — so we fetch the bytes authenticated, wrap them
// in an object URL, and either force a download or open them in a new tab (the PDF preview).

import { blobUrl } from "./explorer";
import { apiFetchBlob } from "./http";

// Types that render INERTLY in a browser tab. A blob: URL inherits THIS origin and scripts inside a
// blob: document execute same-origin — so an uploaded text/html or image/svg+xml opened this way would
// run with access to our stored API token (localStorage). Only these types are ever opened inline;
// anything else (HTML, SVG, text, office docs, unknown) is downloaded instead of rendered.
const INLINE_SAFE_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "image/avif",
]);

/** Wrap a fetched blob in an object URL and trigger a browser download under `filename`. */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Fetch a blob (authenticated) and trigger a browser download under `filename`. */
export async function downloadBlob(hash: string, filename: string): Promise<void> {
  const blob = await apiFetchBlob(blobUrl(hash));
  triggerDownload(blob, filename);
}

/**
 * Fetch a blob (authenticated) and open it inline in a new tab — but ONLY for types that render
 * inertly (PDF, raster images). An uploaded HTML/SVG/text original would execute same-origin from a
 * blob: URL and could steal the API token, so any non-inline-safe type is downloaded instead of
 * rendered. `downloadName` names that fallback download (defaults to the hash).
 */
export async function openBlobInNewTab(hash: string, downloadName?: string): Promise<void> {
  const blob = await apiFetchBlob(blobUrl(hash));
  if (!INLINE_SAFE_TYPES.has(blob.type)) {
    triggerDownload(blob, downloadName ?? hash);
    return;
  }
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  // The new tab holds its own reference; revoke ours later so the object URL isn't leaked forever.
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
