// ====== Code Summary ======
// Layer guard of the frontend import graph (R-32). The dependency direction is
// features -> shell -> components -> hooks / utils / api: a layer may import itself and the layers
// to its right, never one to its left. In particular components/ and shell/ never import from
// features/ (the former inversions — TokenControl -> features/auth, components -> shell — moved the
// shared pieces to hooks/ and components/ instead). A `.test.` file is held to the same rule.
// `theme.ts`, `assets/` and the other top-level modules are leaf modules every layer may use.

import { describe, expect, it } from "vitest";

const LAYERS = ["features", "shell", "components", "hooks", "utils", "api"] as const;
type Layer = (typeof LAYERS)[number];

/** For each layer, the layers it may import (besides itself). */
const MAY_IMPORT: Record<Layer, readonly Layer[]> = {
  features: ["shell", "components", "hooks", "utils", "api"],
  shell: ["components", "hooks", "utils", "api"],
  components: ["hooks", "utils", "api"],
  hooks: ["utils", "api"],
  utils: [],
  api: ["utils"],
};

const sources = import.meta.glob(["./**/*.{ts,tsx}", "!./layering.structure.test.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const IMPORT_SPECIFIER = /(?:from|import|mock)\s*\(?\s*["'](\.{1,2}\/[^"']*)["']/g;

function layerOf(srcPath: string): Layer | null {
  const top = srcPath.split("/")[0];
  return (LAYERS as readonly string[]).includes(top) ? (top as Layer) : null;
}

/** `./components/dialog/Dialog.tsx` + `../../shell/view` -> `shell/view`. */
function resolveFromSrc(importerPath: string, specifier: string): string {
  const parts = importerPath.replace(/^\.\//, "").split("/").slice(0, -1);
  for (const seg of specifier.split("/")) {
    if (seg === "..") parts.pop();
    else if (seg !== ".") parts.push(seg);
  }
  return parts.join("/");
}

function violationsOf(): string[] {
  const found: string[] = [];
  for (const [path, source] of Object.entries(sources)) {
    const from = layerOf(path.replace(/^\.\//, ""));
    if (!from) continue;
    for (const match of source.matchAll(IMPORT_SPECIFIER)) {
      const target = layerOf(resolveFromSrc(path, match[1]));
      if (target && target !== from && !MAY_IMPORT[from].includes(target)) {
        found.push(`${path} (${from}) imports ${match[1]} (${target})`);
      }
    }
  }
  return found;
}

describe("frontend layering", () => {
  it("scans the source tree", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(100);
  });

  it("never imports against features -> shell -> components -> hooks/utils/api", () => {
    expect(violationsOf()).toEqual([]);
  });

  it("keeps the monitoring feature merged into jobs", () => {
    expect(Object.keys(sources).filter((p) => p.startsWith("./features/monitoring/"))).toEqual([]);
  });
});
