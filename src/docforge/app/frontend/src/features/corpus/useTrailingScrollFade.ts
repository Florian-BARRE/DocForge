// ====== Code Summary ======
// Tracks whether an element's scrollable content still extends past its trailing (right) edge —
// drives the corpus grid's edge-fade affordance so off-screen columns stay discoverable. Kept as a
// standalone hook so CorpusTable stays focused on rendering.

import { useEffect, useState, type RefObject } from "react";

export function useTrailingScrollFade(ref: RefObject<HTMLElement | null>, deps: readonly unknown[]): boolean {
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => setCanScrollRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 1);
    update();

    el.addEventListener("scroll", update, { passive: true });
    const resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(el);

    return () => {
      el.removeEventListener("scroll", update);
      resizeObserver.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return canScrollRight;
}
