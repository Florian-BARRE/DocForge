// ====== Code Summary ======
// A full-size overlay showing one page render with forge-orange boxes around a chunk/hit's block
// locations (wraps PageBoxOverlay). Closes on backdrop click or Escape. Reused by the chunk explorer
// and the search results — both point a chunk/hit at its page.

import { useEffect } from "react";
import { PageBoxOverlay, type OverlayBox } from "./PageBoxOverlay";
import { theme } from "../theme";

interface PageBoxLightboxProps {
  renderBlobHash: string | null;
  width?: number | null;
  height?: number | null;
  boxes: OverlayBox[];
  caption: string;
  onClose: () => void;
}

export function PageBoxLightbox({ renderBlobHash, width, height, boxes, caption, onClose }: PageBoxLightboxProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <figure
        onClick={(e) => e.stopPropagation()}
        style={{
          margin: 0, maxWidth: "90vw", maxHeight: "90vh", display: "flex", flexDirection: "column", gap: theme.space.s,
          background: theme.color.panel, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
          padding: theme.space.m, boxShadow: theme.shadow.pop,
        }}
      >
        <PageBoxOverlay
          renderBlobHash={renderBlobHash}
          width={width}
          height={height}
          boxes={boxes}
          alt={caption}
          style={{ maxWidth: "86vw", maxHeight: "76vh" }}
        />
        <figcaption style={{ textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.s }}>
          {caption}
        </figcaption>
      </figure>
    </div>
  );
}
