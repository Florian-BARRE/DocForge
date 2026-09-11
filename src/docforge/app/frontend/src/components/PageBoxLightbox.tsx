// ====== Code Summary ======
// A full-size overlay showing one page render with forge-orange boxes around a chunk/hit's block
// locations (wraps PageBoxOverlay). Closes on backdrop click, Escape, or the visible × button.
// Reused by the chunk explorer and the search results — both point a chunk/hit at its page.
//
// Rendered via a portal straight onto `document.body`. Several page wrappers in this app carry the
// `df-rise` entrance animation (a CSS Animation on `transform`, fill-mode `both`); Chromium treats
// any such element as PERMANENTLY establishing a containing block for `position: fixed` descendants
// (the fill-mode keeps the animation "current" forever, even long after it visually finished), so a
// plain in-tree `position: fixed; inset: 0` here would silently shrink to that ancestor's box instead
// of covering the viewport — exactly what broke the chunk-explorer "view on page" close affordance.
// A portal sidesteps the whole containing-block class of bug regardless of what ancestors do.

import { useId } from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "../shell/useFocusTrap";
import { PageBoxOverlay, type OverlayBox } from "./PageBoxOverlay";
import { theme } from "../theme";

interface PageBoxLightboxProps {
  renderBlobHash: string | null;
  width?: number | null;
  height?: number | null;
  boxes: OverlayBox[];
  caption: string;
  onClose: () => void;
  /** Navigate to the previous/next page without closing — omit both on a caller with no natural
   *  page sequence (e.g. a single search hit's page). Left/Right arrow keys mirror the buttons. */
  onPrev?: () => void;
  onNext?: () => void;
}

const navButtonStyle: React.CSSProperties = {
  position: "absolute", top: "50%", transform: "translateY(-50%)", width: 36, height: 36,
  display: "flex", alignItems: "center", justifyContent: "center",
  background: theme.color.panel, color: theme.color.text,
  border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.pill,
  fontSize: theme.font.size.l, lineHeight: 1, cursor: "pointer", boxShadow: theme.shadow.pop,
};

export function PageBoxLightbox({ renderBlobHash, width, height, boxes, caption, onClose, onPrev, onNext }: PageBoxLightboxProps) {
  const captionId = useId();
  // Replaces the primitive's own window-level Escape listener — `useFocusTrap` covers Escape plus
  // Tab-cycling and focus restore in one place.
  const figureRef = useFocusTrap<HTMLElement>(onClose);

  return createPortal(
    <div
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft" && onPrev) { e.preventDefault(); onPrev(); }
        else if (e.key === "ArrowRight" && onNext) { e.preventDefault(); onNext(); }
      }}
      style={{
        position: "fixed", inset: 0, background: theme.color.overlay, backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <figure
        ref={figureRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={captionId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "relative", margin: 0, maxWidth: "90vw", maxHeight: "90vh",
          display: "flex", flexDirection: "column", gap: theme.space.s,
          background: theme.color.panel, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
          padding: theme.space.m, boxShadow: theme.shadow.pop,
        }}
      >
        <button
          type="button"
          onClick={onClose}
          title="Close"
          aria-label="Close"
          style={{
            position: "absolute", top: -12, right: -12, width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: theme.color.panel, color: theme.color.text,
            border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.pill,
            fontSize: theme.font.size.l, lineHeight: 1, cursor: "pointer", boxShadow: theme.shadow.pop,
          }}
        >
          ×
        </button>
        {onPrev && (
          <button type="button" onClick={onPrev} title="Previous page" aria-label="Previous page" style={{ ...navButtonStyle, left: -18 }}>
            ‹
          </button>
        )}
        {onNext && (
          <button type="button" onClick={onNext} title="Next page" aria-label="Next page" style={{ ...navButtonStyle, right: -18 }}>
            ›
          </button>
        )}
        <PageBoxOverlay
          renderBlobHash={renderBlobHash}
          width={width}
          height={height}
          boxes={boxes}
          alt={caption}
          style={{ maxWidth: "86vw", maxHeight: "76vh" }}
        />
        <figcaption id={captionId} style={{ textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.s }}>
          {caption}
        </figcaption>
      </figure>
    </div>,
    document.body,
  );
}
