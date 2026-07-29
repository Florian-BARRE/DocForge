// ====== Code Summary ======
// A responsive grid of page thumbnails; click a rendered page to open it in the lightbox.

import { useState } from "react";
import type { PageInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { PageLightbox } from "./PageLightbox";
import { PageThumbnail } from "./PageThumbnail";

export function PagesTab({ pages }: { pages: PageInfo[] }) {
  const [openPage, setOpenPage] = useState<PageInfo | null>(null);

  if (!pages.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No pages recorded.</div>;

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: theme.space.l }}>
        {pages.map((page) => (
          <PageThumbnail key={page.page_number} page={page} onClick={() => setOpenPage(page)} />
        ))}
      </div>
      {openPage && <PageLightbox page={openPage} onClose={() => setOpenPage(null)} />}
    </>
  );
}
