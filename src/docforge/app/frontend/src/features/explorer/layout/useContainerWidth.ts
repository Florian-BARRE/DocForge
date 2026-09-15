// ====== Code Summary ======
// Measures an element's own content width via ResizeObserver — the same width-tracking pattern
// CorpusTable uses for its scroll wrapper, generalised here so PageGroupRow can size its page-zoom
// "fit" baseline (pageZoom.ts) off the page column's live measured width.

import { useEffect, useRef, useState, type RefObject } from "react";

export function useContainerWidth<T extends HTMLElement>(): [RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => setWidth(entries[0]?.contentRect.width ?? 0));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return [ref, width];
}
