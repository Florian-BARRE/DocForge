// ====== Code Summary ======
// Tracks which stage card is currently in view, for the minimap's highlight. An IntersectionObserver
// rooted on the rail's own scroll container (not the viewport — the rail scrolls internally, see
// StageRailPage) watches every stage anchor; the active key is the first stage (in canonical run
// order) currently intersecting a band near the top of that container. Falls back to the first
// stage key immediately (before any observation fires) so the minimap never starts with nothing
// highlighted.

import { useEffect, useState, type RefObject } from "react";
import { stageAnchorId } from "./stageAnchor";

export function useActiveStageKey(stageKeys: string[], containerRef: RefObject<HTMLElement>): string | null {
  const [activeKey, setActiveKey] = useState<string | null>(null);

  useEffect(() => {
    if (stageKeys.length === 0) return;
    setActiveKey((current) => (current && stageKeys.includes(current) ? current : stageKeys[0]));

    const root = containerRef.current;
    // jsdom (unit tests) has no IntersectionObserver unless a test polyfill stubs it — the fallback
    // above already picked a sane default, so this simply never refines it further there.
    if (!root || typeof IntersectionObserver === "undefined") return;

    const elements = stageKeys
      .map((key) => document.getElementById(stageAnchorId(key)))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const visibleIds = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visibleIds.add(entry.target.id);
          else visibleIds.delete(entry.target.id);
        }
        const firstVisibleKey = stageKeys.find((key) => visibleIds.has(stageAnchorId(key)));
        if (firstVisibleKey) setActiveKey(firstVisibleKey);
      },
      // Biases toward "has reached the top band" rather than "is anywhere on screen" — a tall card
      // stays the active one until its successor's header actually crosses near the top.
      { root, rootMargin: "-8% 0px -70% 0px", threshold: 0 },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [stageKeys, containerRef]);

  return activeKey;
}
