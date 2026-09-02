// ====== Code Summary ======
// Renders a page render image with forge-orange rectangles drawn around one or more chunk/hit block
// locations. Boxes are positioned in PERCENT of the image box (bbox is normalised [0,1]), so they
// track the image as it scales — no pixel maths, no resize listeners.
//
// The size constraints live on the IMAGE (not the wrapper): the image renders at the page aspect
// ratio and fits within the caller's max box with NO letterboxing, and the wrapper shrink-wraps it.
// A box's % is therefore always a % of the actual displayed image rect. (Putting the constraints on
// the wrapper + object-fit:contain letterboxed the image inside a wrong-ratio box, so boxes drifted
// off their blocks on pages whose ratio differed from the clamped box.) Degrades gracefully when the
// page has no render (HTML pre-fix docs): shows a muted note instead of a broken image.

import { BlobImage } from "./BlobImage";
import { theme } from "../theme";

/** One rectangle to draw — a bounding box normalised to [0, 1] as [x0, y0, x1, y1]. */
export interface OverlayBox {
  bbox: number[];
  /** The single primary/matched block draws in full forge-orange; any other box on the same call
   *  (e.g. a chunk's other spanned blocks) draws muted so only ONE thing reads as "the match" (per
   *  brand.md — orange marks the one thing being worked, never a uniform decoration). Defaults to
   *  `true` so existing single/uniform-box callers are unaffected. */
  primary?: boolean;
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
    <div style={{ position: "relative", display: "inline-block", lineHeight: 0 }}>
      <BlobImage
        hash={renderBlobHash}
        alt={alt}
        // Size constraints (max-width/height, usually vw/vh) come from the caller via `style` and are
        // applied HERE so the image fits the max box at the page aspect ratio with no letterboxing;
        // object-fit:fill maps the raster onto the page-ratio box exactly (a no-op when the render's
        // raster ratio already equals the page ratio). The wrapper then shrink-wraps this exact rect.
        style={{ display: "block", width: "auto", height: "auto", aspectRatio, objectFit: "fill", borderRadius: theme.radius.m, ...style }}
      />
      {boxes.map((box, index) => {
        const [x0, y0, x1, y1] = box.bbox;
        const left = clamp01(x0);
        const top = clamp01(y0);
        const right = clamp01(x1);
        const bottom = clamp01(y1);
        const isPrimary = box.primary !== false;
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: `${left * 100}%`,
              top: `${top * 100}%`,
              width: `${Math.max(0, right - left) * 100}%`,
              height: `${Math.max(0, bottom - top) * 100}%`,
              border: isPrimary ? `2px solid ${theme.color.accent}` : `1.5px dashed ${theme.color.lineStrong}`,
              borderRadius: theme.radius.s,
              boxShadow: isPrimary ? `0 0 0 1px ${theme.color.accentSoft}` : "none",
              pointerEvents: "none",
            }}
          />
        );
      })}
    </div>
  );
}
