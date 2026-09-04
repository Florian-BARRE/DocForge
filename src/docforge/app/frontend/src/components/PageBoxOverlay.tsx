// ====== Code Summary ======
// Renders a page render image with rectangles drawn around one or more chunk/hit block locations.
// Boxes are positioned in PERCENT of the image box (bbox is normalised [0,1]), so they track the image
// as it scales — no pixel maths, no resize listeners.
//
// The size constraints live on the IMAGE (not the wrapper): the image renders at the page aspect ratio
// and fits within the caller's max box with NO letterboxing. Degrades gracefully when the page has no
// render (HTML pre-fix docs): shows a muted note instead of a broken image.
//
// Layout-view boxes: thin solid outline per block (type colour) with a small number tab ABOVE a corner
// (never inside, never over the box's own text); chunk grouping boxes draw as a DASHED container in the
// distinct chunk-outline colour, labelled "Chunk N" above the corner. The forge accent marks the active
// one; the rest dim.

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
  /** Per-box border colour (a theme token). When set it overrides the primary/muted styling — used
   *  by the Layout view to colour every block's box by its type. Omit for the default behaviour. */
  color?: string;
  /** A short label drawn on a small tab ABOVE the box's corner (block number / "Chunk N"). */
  label?: string;
  /** Emphasise this box (thicker border + soft ring) — the Layout view sets it on the active block. */
  active?: boolean;
  /** `"group"` draws a DASHED container box (the chunk grouping in the Layout view). Default `"block"`. */
  variant?: "block" | "group";
  /** When set, the box becomes clickable (cursor + keyboard) and calls this on activation. */
  onSelect?: () => void;
  /** Accessible label for a clickable box (e.g. "Block 3, Heading"). */
  selectLabel?: string;
  /** Recede this box (low opacity, no label) — the Layout view dims everything outside the selection. */
  dim?: boolean;
}

interface PageBoxOverlayProps {
  renderBlobHash: string | null;
  width?: number | null;
  height?: number | null;
  boxes: OverlayBox[];
  alt: string;
  /** Applied to the IMAGE — the caller constrains size here (e.g. maxWidth / maxHeight). */
  style?: React.CSSProperties;
  /** Passed through to `BlobImage` — defer the fetch until scrolled near view. See its own doc. */
  lazy?: boolean;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function PageBoxOverlay({ renderBlobHash, width, height, boxes, alt, style, lazy }: PageBoxOverlayProps) {
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
        lazy={lazy}
        style={{ display: "block", width: "auto", height: "auto", aspectRatio, objectFit: "fill", borderRadius: theme.radius.m, ...style }}
      />
      {boxes.map((box, index) => {
        const [x0, y0, x1, y1] = box.bbox;
        const left = clamp01(x0);
        const top = clamp01(y0);
        const right = clamp01(x1);
        const bottom = clamp01(y1);
        const isPrimary = box.primary !== false;
        const isGroup = box.variant === "group";
        const isLayout = Boolean(box.color) || isGroup;
        const dim = box.dim === true;
        const stroke = box.color ?? (isPrimary ? theme.color.accent : theme.color.lineStrong);

        // Thin solid block outline; DASHED chunk container; legacy primary(solid)/muted(dashed) untouched.
        let border: string;
        let background = "transparent";
        let boxShadow = "none";
        if (isGroup) {
          // Outline only — the dashed chunk container never fills its background (it would tint the
          // page content it encloses); the forge accent on its border is enough when active.
          border = `${box.active ? 2 : 1.25}px dashed ${stroke}`;
        } else if (box.color) {
          border = `${box.active ? 2 : 1}px solid ${stroke}`;
          if (box.active) {
            background = theme.color.accentSoft;
            boxShadow = `0 0 0 3px ${theme.color.accentSoft}`;
          }
        } else {
          border = isPrimary ? `2px solid ${stroke}` : `1.5px dashed ${stroke}`;
          if (isPrimary) boxShadow = `0 0 0 1px ${theme.color.accentSoft}`;
        }

        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: `${left * 100}%`,
              top: `${top * 100}%`,
              width: `${Math.max(0, right - left) * 100}%`,
              height: `${Math.max(0, bottom - top) * 100}%`,
              border,
              borderRadius: isGroup ? theme.radius.m : theme.radius.s,
              boxShadow,
              background,
              zIndex: isGroup ? 0 : box.active ? 2 : 1,
              opacity: dim ? 0.22 : 1,
              transition: "opacity .12s ease, border-color .12s ease",
              pointerEvents: box.onSelect ? "auto" : "none",
              cursor: box.onSelect ? "pointer" : "default",
            }}
            {...(box.onSelect
              ? {
                  role: "button" as const,
                  tabIndex: 0,
                  "aria-label": box.selectLabel,
                  onClick: box.onSelect,
                  onKeyDown: (event: React.KeyboardEvent) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      box.onSelect?.();
                    }
                  },
                }
              : {})}
          >
            {box.label && !dim && (
              <span
                style={{
                  position: "absolute",
                  // The tab sits ABOVE a corner of the box (block → top-left, chunk → top-right), never
                  // inside the box or over its own text.
                  top: 0,
                  transform: "translateY(-100%)",
                  ...(isGroup ? { right: -1 } : { left: -1 }),
                  fontFamily: theme.font.mono,
                  fontSize: theme.font.size.xs,
                  lineHeight: 1.45,
                  padding: "0 4px",
                  color: theme.color.onAccent,
                  background: stroke,
                  borderRadius: isLayout ? `${theme.radius.s}px ${theme.radius.s}px 0 0` : theme.radius.s,
                  whiteSpace: "nowrap",
                  boxShadow: isLayout ? "0 1px 2px rgba(0,0,0,0.28)" : "none",
                }}
              >
                {box.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
