// ====== Code Summary ======
// A responsive grid of page thumbnails; click a rendered page to open it in the shared box-less
// lightbox (PageBoxLightbox with an empty box list — this tab has no chunk/hit to outline).

import { useState } from "react";
import type { PageInfo } from "../../../api/explorer";
import { PageBoxLightbox } from "../../../components/PageBoxLightbox";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { PageThumbnail } from "./PageThumbnail";

export function PagesTab({ pages }: { pages: PageInfo[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const openPage = openIndex === null ? null : pages[openIndex];

  if (!pages.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No pages recorded.</div>;

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: theme.space.l }}>
        {pages.map((page, index) => (
          <PageThumbnail key={page.page_number} page={page} onClick={() => setOpenIndex(index)} />
        ))}
      </div>
      {openPage && openIndex !== null && (
        <PageBoxLightbox
          renderBlobHash={openPage.render_blob_hash}
          width={openPage.width}
          height={openPage.height}
          boxes={[]}
          caption={`Page ${displayPage(openPage.page_number)}`}
          onClose={() => setOpenIndex(null)}
          onPrev={openIndex > 0 ? () => setOpenIndex(openIndex - 1) : undefined}
          onNext={openIndex < pages.length - 1 ? () => setOpenIndex(openIndex + 1) : undefined}
        />
      )}
    </>
  );
}
