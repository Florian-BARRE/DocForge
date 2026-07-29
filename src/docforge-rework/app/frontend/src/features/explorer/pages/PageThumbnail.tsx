// ====== Code Summary ======
// One page's thumbnail in the grid — the rasterized render when available, a placeholder when
// the render stage was off for this document. Click opens the lightbox at full size.

import { useState } from "react";
import { BlobImage } from "../../../components/BlobImage";
import { type PageInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { displayPage } from "../format";

export function PageThumbnail({ page, onClick }: { page: PageInfo; onClick: () => void }) {
  const [hover, setHover] = useState(false);
  const clickable = Boolean(page.render_blob_hash);

  return (
    <div
      onClick={clickable ? onClick : undefined}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ display: "flex", flexDirection: "column", gap: 6, cursor: clickable ? "pointer" : "default" }}
    >
      <div
        style={{
          background: theme.color.surface, border: `1px solid ${hover && clickable ? theme.color.accentLine : theme.color.line}`,
          borderRadius: theme.radius.m, boxShadow: hover && clickable ? theme.shadow.md : theme.shadow.sm,
          transform: hover && clickable ? "translateY(-2px)" : "none",
          transition: "transform .15s ease, box-shadow .15s ease, border-color .15s ease",
          aspectRatio: page.width && page.height ? `${page.width} / ${page.height}` : "3 / 4",
          overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        {page.render_blob_hash ? (
          <BlobImage
            hash={page.render_blob_hash}
            alt={`Page ${displayPage(page.page_number)}`}
            style={{ width: "100%", height: "100%", objectFit: "contain" }}
          />
        ) : (
          <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>no render</span>
        )}
      </div>
      <div style={{ textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.xs }}>
        Page {displayPage(page.page_number)}{page.is_scanned ? " · scanned" : ""}
      </div>
    </div>
  );
}
