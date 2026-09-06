// Vitest global setup — extends `expect` with jest-dom's DOM matchers for every test file.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup-after-each relies on a global test framework being detected; this project
// runs vitest WITHOUT `test.globals` (explicit imports everywhere, matching the codebase's
// explicit-over-implicit convention), so that auto-registration never fires — wire it manually or
// every test file's DOM leaks into the next one within the same file.
afterEach(cleanup);

// jsdom implements neither API — needed by the stage rail's minimap (`useActiveStageKey` observes
// stage anchors; clicking a minimap entry calls `scrollIntoView`). Both are inert no-ops here: the
// tests that exercise them assert on the resulting DOM/callbacks, not on real intersection/scroll.
if (typeof globalThis.IntersectionObserver === "undefined") {
  class MockIntersectionObserver implements IntersectionObserver {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: number[] = [];
    disconnect(): void {}
    observe(): void {}
    takeRecords(): IntersectionObserverEntry[] {
      return [];
    }
    unobserve(): void {}
  }
  globalThis.IntersectionObserver = MockIntersectionObserver;
}
if (typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom implements neither API — needed by the corpus grid (CorpusTable measures its scroll
// wrapper's width via `ResizeObserver` to size the virtualized `<table>`; `@tanstack/react-virtual`
// itself also expects the constructor to exist). Inert no-op: the tests that exercise the grid
// assert on rendered rows/columns, not on real resize notifications.
if (typeof globalThis.ResizeObserver === "undefined") {
  class MockResizeObserver implements ResizeObserver {
    disconnect(): void {}
    observe(): void {}
    unobserve(): void {}
  }
  globalThis.ResizeObserver = MockResizeObserver;
}
