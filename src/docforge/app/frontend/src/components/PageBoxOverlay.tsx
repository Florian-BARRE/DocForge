// ====== Code Summary ======
// Renders a page render image with forge-orange rectangles drawn around one or more chunk/hit block
// locations. Boxes are positioned in PERCENT of the image box (bbox is normalised [0,1]), so they
// track the image as it scales — no pixel maths, no resize listeners. The wrapper shrink-wraps the
// image so a box's % is always a % of the rendered image. Degrades gracefully when the page has no
// render (HTML pre-fix docs): shows a muted note instead of a broken image.

import { BlobImage } from "./BlobImage";
import { theme } from "../theme";

/** One rectangle to draw — a bounding box normalised to [0, 1] as [x0, y0, x1, y1]. */
export interface OverlayBox {
  bbox: number[];
}

interface PageBoxOverlayProps {
  renderBlobHash: string | null;
  width?: number | null;
  height?: number | null;
  boxes: OverlayBox[];
  alt: string;
  /** Applied to the wrapper — the caller constrains size here (e.g. maxWidth / maxHeight). */
  style?: React.CSSProperties;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function PageBoxOverlay({ renderBlobHash, width, height, boxes, alt, style }: PageBoxOverlayProps) {
  if (!renderBlobHash) {
    return (
      <div
        style={{
          ...style,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: theme.color.dim,
          fontSize: theme.font.size.s,
          background: theme.color.panel,
          border: `1px dashed ${theme.color.line}`,
          borderRadius: theme.radius.m,
          padding: theme.space.l,
          textAlign: "center",
        }}
      >
        No page render for this document — showing text only.
      </div>
    );
  }

  const aspectRatio = width && height ? `${width} / ${height}` : undefined;

  return (
    <div style={{ position: "relative", display: "inline-block", lineHeight: 0, ...style }}>
      <BlobImage
        hash={renderBlobHash}
        alt={alt}
        style={{ width: "100%", height: "100%", objectFit: "contain", display: "block", aspectRatio, borderRadius: theme.radius.m }}
      />
      {boxes.map((box, index) => {
        const [x0, y0, x1, y1] = box.bbox;
        const left = clamp01(x0);
        const top = clamp01(y0);
        const right = clamp01(x1);
        const bottom = clamp01(y1);
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: `${left * 100}%`,
              top: `${top * 100}%`,
              width: `${Math.max(0, right - left) * 100}%`,
              height: `${Math.max(0, bottom - top) * 100}%`,
              border: `2px solid ${theme.color.accent}`,
              borderRadius: theme.radius.s,
              boxShadow: `0 0 0 1px ${theme.color.accentSoft}`,
              pointerEvents: "none",
            }}
          />
        );
      })}
    </div>
  );
}
