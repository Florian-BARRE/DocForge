// ====== Code Summary ======
// A clickable reference to a content-addressed blob object found inside a trace payload — an
// inline thumbnail (via the shared `BlobImage`) when the field name hints the blob is an image
// (a page render, a figure crop), otherwise a small "view / download" chip. Both open the real
// object through the existing authenticated blob mechanism (`openBlobInNewTab` — inline for
// PDF/raster images, downloaded otherwise for anything else, e.g. an original source file).
// Reused by `TracePayloadNode` wherever the payload walk recognizes a blob-hash value.

import { useState } from "react";
import { openBlobInNewTab } from "../../api/blobs";
import { BlobImage } from "../../components/BlobImage";
import { theme } from "../../theme";

// Truncation length for the hash shown on the chip/thumbnail title — same convention as
// JobEventDetail's own shape-summary hash display.
const HASH_DISPLAY_LENGTH = 12;

interface BlobRefChipProps {
  hash: string;
  /** The field name this hash was found under (e.g. "render_blob_hash") — used as the download
   *  filename stem and shown in the tooltip. */
  fieldName: string;
  /** True when the field name hints this blob is an image (page render, figure crop, thumbnail) —
   *  renders an inline thumbnail instead of a plain view/download chip. */
  image: boolean;
}

export function BlobRefChip({ hash, fieldName, image }: BlobRefChipProps) {
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    setError(null);
    try {
      await openBlobInNewTab(hash, `${fieldName}-${hash.slice(0, HASH_DISPLAY_LENGTH)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open blob.");
    }
  };

  if (image) {
    return (
      <div style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
        <button
          type="button"
          onClick={open}
          title={`${fieldName}: ${hash}`}
          aria-label={`Open ${fieldName} blob`}
          style={{
            background: "none", border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
            padding: 2, cursor: "pointer", lineHeight: 0,
          }}
        >
          <BlobImage
            hash={hash}
            alt={fieldName}
            style={{ width: 72, height: 72, objectFit: "cover", borderRadius: theme.radius.s }}
            lazy
          />
        </button>
        {error && <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>}
      </div>
    );
  }

  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
      <button
        type="button"
        onClick={open}
        title={`${fieldName}: ${hash}`}
        style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          background: theme.color.accentSoft, color: theme.color.accentSafe,
          border: `1px solid ${theme.color.accentLine}`, borderRadius: theme.radius.pill,
          padding: "2px 9px", fontSize: theme.font.size.xs, fontFamily: theme.font.mono,
          cursor: "pointer",
        }}
      >
        view/download · {hash.slice(0, HASH_DISPLAY_LENGTH)}…
      </button>
      {error && <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>}
    </span>
  );
}
