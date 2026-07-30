// ====== Code Summary ======
// A minimal full-size overlay for one page render — closes on backdrop click or Escape.

import { useEffect } from "react";
import { type PageInfo } from "../../../api/explorer";
import { BlobImage } from "../../../components/BlobImage";
import { theme } from "../../../theme";
import { displayPage } from "../format";

interface PageLightboxProps {
  page: PageInfo;
  onClose: () => void;
}

export function PageLightbox({ page, onClose }: PageLightboxProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!page.render_blob_hash) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <figure
        style={{
          margin: 0, maxWidth: "90vw", maxHeight: "90vh", display: "flex", flexDirection: "column", gap: theme.space.s,
          background: theme.color.panel, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
          padding: theme.space.m, boxShadow: theme.shadow.pop,
        }}
      >
        <BlobImage
          hash={page.render_blob_hash}
          alt={`Page ${displayPage(page.page_number)}`}
          style={{ maxWidth: "86vw", maxHeight: "76vh", objectFit: "contain", borderRadius: theme.radius.m }}
        />
        <figcaption style={{ textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.s }}>
          Page {displayPage(page.page_number)}
        </figcaption>
      </figure>
    </div>
  );
}
