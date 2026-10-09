// ====== Code Summary ======
// Deep-link round-trips for the collection Settings sub-tabs (`/collections/:id/settings[/section]`):
// each section serializes to its own hash and parses back; "general" is the bare default; an unknown
// sub-segment and the legacy `/edit` hash fall back to the default sub-tab instead of a dead screen.

import { describe, expect, it } from "vitest";
import { parseViewFromHash, serializeViewToHash } from "./urlSync";
import type { View } from "./view";

describe("collection Settings sub-tab routing", () => {
  it.each(["aliases", "history", "transfer"] as const)("round-trips the %s section", (section) => {
    const view: View = { name: "collection-settings", collectionId: "c1", section };
    const hash = serializeViewToHash(view);
    expect(hash).toBe(`/collections/c1/settings/${section}`);
    expect(parseViewFromHash(`#${hash}`)).toEqual(view);
  });

  it("serializes general (and an absent section) to the bare settings path", () => {
    expect(serializeViewToHash({ name: "collection-settings", collectionId: "c1", section: "general" })).toBe("/collections/c1/settings");
    expect(serializeViewToHash({ name: "collection-settings", collectionId: "c1" })).toBe("/collections/c1/settings");
    expect(parseViewFromHash("#/collections/c1/settings")).toEqual({ name: "collection-settings", collectionId: "c1" });
  });

  it("falls back to the default sub-tab for an unknown segment and the legacy /edit hash", () => {
    expect(parseViewFromHash("#/collections/c1/settings/nope")).toEqual({ name: "collection-settings", collectionId: "c1" });
    expect(parseViewFromHash("#/collections/c1/edit")).toEqual({ name: "collection-settings", collectionId: "c1" });
  });
});
