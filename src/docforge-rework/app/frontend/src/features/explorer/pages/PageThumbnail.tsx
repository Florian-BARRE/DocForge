// ====== Code Summary ======
// One page's thumbnail in the grid — the rasterized render when available, a placeholder when
// the render stage was off for this document. Click opens the lightbox at full size.

import { blobUrl, type PageInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { displayPage } from "../format";

export function PageThumbnail({ page, onClick }: { page: PageInfo; onClick: () => void }) {
  return (
    <div
      onClick={page.render_blob_hash ? onClick : undefined}
      style={{ display: "flex", flexDirection: "column", gap: 4, cursor: page.render_blob_hash ? "pointer" : "default" }}
    >
      <div
        style={{
          background: theme.color.card, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
          aspectRatio: page.width && page.height ? `${page.width} / ${page.height}` : "3 / 4",
          overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center",
        }}
      >
        {page.render_blob_hash ? (
          <img
            src={blobUrl(page.render_blob_hash)}
            loading="lazy"
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
