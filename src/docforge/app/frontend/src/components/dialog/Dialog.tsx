// ====== Code Summary ======
// The modal shell every dialog of the app renders through: a full-viewport overlay, one centred (or
// top-anchored) panel with `role="dialog"` `aria-modal="true"`, the `useFocusTrap` keyboard behaviour
// (focus moved in and restored, Tab cycling, Escape closes), a body scroll lock, an optional backdrop
// click that closes, and an optional corner "×" close button that is disabled while an operation is
// pending. It owns only the shell; the content (title, body, buttons) is the caller's, so a feature
// dialog keeps its own copy and logic — `ConfirmDialog` is the shell + a confirm/cancel footer.
//
// Portaled to `document.body` by default: several page wrappers carry the `df-rise` entrance CSS
// animation, which silently confines an in-tree `position: fixed` overlay to that ancestor's box in
// Chromium (see PageBoxLightbox.tsx). `portal={false}` keeps the legacy in-tree render for the
// dialogs that were never portaled.

// ====== Third-Party Library Imports ======
import { useId, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

// ====== Internal Project Imports ======
import { useFocusTrap } from "../../shell/useFocusTrap";
import { theme } from "../../theme";

// ====== Local Project Imports ======
import { DialogTitle } from "./DialogTitle";
import { useBodyScrollLock } from "./useBodyScrollLock";

/** The panel's border colour: neutral line, forge accent, or error (destructive). */
export type DialogTone = "neutral" | "accent" | "danger";

const TONE_BORDER: Record<DialogTone, string> = {
  neutral: theme.color.line,
  accent: theme.color.accentLine,
  danger: theme.color.error,
};

export interface DialogProps {
  /** Closes the dialog: Escape, the backdrop click and the "×" button all call it. */
  onClose: () => void;
  /** Heading rendered as the dialog's `<h2>`, which also labels it. Omit when `labelledBy` or `ariaLabel` is used. */
  title?: ReactNode;
  /** `id` of a heading rendered by the caller (custom header). */
  labelledBy?: string;
  ariaLabel?: string;
  tone?: DialogTone;
  maxWidth?: number;
  /** Blurs the page behind the overlay. Default true. */
  blur?: boolean;
  /** A click on the overlay (outside the panel) calls `onClose`. Default true. */
  closeOnBackdrop?: boolean;
  /** Renders the corner "×" close button. Default false. */
  showClose?: boolean;
  /** Disables the "×" button — e.g. while the dialog's operation is pending. */
  closeDisabled?: boolean;
  /** Portal to `document.body`. Default true. */
  portal?: boolean;
  /** `top` anchors the panel under the viewport top (command palette); default `center`. */
  placement?: "center" | "top";
  /** CSS z-index of the overlay. Default 100. */
  layer?: number;
  /** The panel's element: a `<figure>` for the lightbox. Default `div`. */
  panelAs?: "div" | "figure";
  /** Merged over the default panel style (padding, gap, width 100%…). */
  panelStyle?: CSSProperties;
  /** Keydown on the overlay (arrow-key navigation of the lightbox). */
  onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void;
  children: ReactNode;
}

const closeButtonStyle = (disabled: boolean): CSSProperties => ({
  position: "absolute", top: -12, right: -12, width: 28, height: 28,
  display: "flex", alignItems: "center", justifyContent: "center",
  background: theme.color.panel, color: theme.color.text,
  border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.pill,
  fontSize: theme.font.size.l, lineHeight: 1, cursor: disabled ? "not-allowed" : "pointer",
  boxShadow: theme.shadow.pop,
});

export function Dialog({
  onClose, title, labelledBy, ariaLabel, tone = "neutral", maxWidth = 480, blur = true, closeOnBackdrop = true,
  showClose = false, closeDisabled = false, portal = true, placement = "center", layer = 100, panelAs = "div",
  panelStyle, onKeyDown, children,
}: DialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLElement>(onClose);
  useBodyScrollLock();
  const Panel = panelAs as "div";

  const overlay = (
    <div
      onClick={closeOnBackdrop ? onClose : undefined}
      onKeyDown={onKeyDown}
      style={{
        position: "fixed", inset: 0, background: theme.color.overlay, ...(blur ? { backdropFilter: "blur(2px)" } : {}), zIndex: layer,
        display: "flex", alignItems: placement === "top" ? "flex-start" : "center", justifyContent: "center",
        padding: placement === "top" ? theme.space.xxl : theme.space.l,
      }}
    >
      <Panel
        ref={panelRef as React.RefObject<HTMLDivElement>}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title !== undefined ? titleId : labelledBy}
        aria-label={ariaLabel}
        tabIndex={-1}
        onClick={closeOnBackdrop ? (e) => e.stopPropagation() : undefined}
        style={{
          ...(showClose ? { position: "relative" } : {}),
          background: theme.color.panel, border: `1px solid ${TONE_BORDER[tone]}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
          ...panelStyle,
        }}
      >
        {showClose && (
          <button type="button" onClick={onClose} disabled={closeDisabled} title="Close" aria-label="Close" style={closeButtonStyle(closeDisabled)}>
            ×
          </button>
        )}
        {title !== undefined && <DialogTitle id={titleId}>{title}</DialogTitle>}
        {children}
      </Panel>
    </div>
  );

  return portal ? createPortal(overlay, document.body) : overlay;
}
