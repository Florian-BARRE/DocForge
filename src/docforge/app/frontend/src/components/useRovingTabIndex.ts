// ====== Code Summary ======
// Roving-tabindex keyboard navigation for a one-dimensional widget (a tablist, a segmented
// control…) — Left/Right/Home/End move focus among a fixed-order set of item elements. This app's
// tabs switch on a single click already, so moving focus also activates the item (automatic
// activation, the standard WAI-ARIA tabs model) — the caller's `onActivate` is invoked on every
// move, matching the existing click-to-switch behaviour instead of adding a second interaction
// model. Shared by `TabNav` and any bespoke tablist (e.g. `CollectionShell`'s level-1 section row).

import { useRef, type KeyboardEvent } from "react";

export interface RovingTabIndex<K extends string> {
  /** Ref callback to attach to each item's focusable element, keyed by its item key. */
  register: (key: K) => (el: HTMLElement | null) => void;
  /** Keydown handler to attach to each item's focusable element, given that item's key. */
  onKeyDown: (e: KeyboardEvent, currentKey: K) => void;
}

export function useRovingTabIndex<K extends string>(order: K[], onActivate: (key: K) => void): RovingTabIndex<K> {
  const elements = useRef<Map<K, HTMLElement>>(new Map());

  const register = (key: K) => (el: HTMLElement | null) => {
    if (el) elements.current.set(key, el);
    else elements.current.delete(key);
  };

  const focusAt = (index: number) => {
    const key = order[(index + order.length) % order.length];
    const el = elements.current.get(key);
    el?.focus();
    onActivate(key);
  };

  const onKeyDown = (e: KeyboardEvent, currentKey: K) => {
    const index = order.indexOf(currentKey);
    if (index === -1) return;
    switch (e.key) {
      case "ArrowRight":
        e.preventDefault();
        focusAt(index + 1);
        break;
      case "ArrowLeft":
        e.preventDefault();
        focusAt(index - 1);
        break;
      case "Home":
        e.preventDefault();
        focusAt(0);
        break;
      case "End":
        e.preventDefault();
        focusAt(order.length - 1);
        break;
    }
  };

  return { register, onKeyDown };
}
