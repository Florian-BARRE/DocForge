// ====== Code Summary ======
// Focus-trap primitive for modal dialogs/lightboxes — on mount it moves focus into the dialog,
// cycles Tab/Shift-Tab within it, closes on Escape, and restores focus to whatever triggered the
// dialog once it unmounts. Every dialog in the app is conditionally mounted (`{open && <Dialog/>}`
// — see CreatedKeyModal, BulkConfirmDialog, PageBoxLightbox), so a mount-once effect that closes
// over the `onClose` from the first render is safe: a fresh instance mounts each time it opens.
//
// Usage: attach the returned ref to the dialog's own panel element (not the backdrop) and pair it
// with `role="dialog"` `aria-modal="true"` `aria-labelledby={titleId}` — this hook only owns
// keyboard/focus behaviour, never markup or styling, so it drops into any existing dialog shape.

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

export function useFocusTrap<T extends HTMLElement>(onClose: () => void): RefObject<T> {
  const containerRef = useRef<T>(null);

  useEffect(() => {
    const triggerElement = document.activeElement;
    const container = containerRef.current;

    // 1. Move focus into the dialog — the first focusable descendant, or the panel itself as a
    // fallback (it needs `tabIndex={-1}` on the element for that to actually be focusable).
    const first = container ? focusableElements(container)[0] ?? container : null;
    first?.focus();

    // 2. Escape closes; Tab/Shift-Tab cycles within the dialog instead of escaping to the page.
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !container) return;
      const focusable = focusableElements(container);
      if (focusable.length === 0) return;
      const firstEl = focusable[0];
      const lastEl = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    // 3. On unmount, hand focus back to whatever opened the dialog.
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (triggerElement instanceof HTMLElement) triggerElement.focus();
    };
    // Deliberately mount-once — see the module comment on why closing over the initial `onClose` is safe.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return containerRef;
}
