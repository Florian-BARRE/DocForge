// ====== Code Summary ======
// Covers the iteration-2 GUI campaign regression: editing a collection without touching the
// size-limit field must never rewrite `max_file_size_bytes` through a rounded-MiB round-trip.

import { describe, expect, it } from "vitest";
import { bytesToMb, resolveMaxFileSizeBytes } from "./wizardTypes";

describe("resolveMaxFileSizeBytes", () => {
  it("preserves the exact original bytes when the displayed MiB value is untouched", () => {
    const original = 20_000_000; // -> "19.07" MiB rounded for display
    const displayedMb = bytesToMb(original);
    expect(resolveMaxFileSizeBytes(displayedMb, original)).toBe(original);
  });

  it("re-derives bytes from MiB once the user actually changes the value", () => {
    const original = 20_000_000;
    expect(resolveMaxFileSizeBytes(25, original)).toBe(25 * 1024 * 1024);
  });

  it("always derives from MiB when there is no original (create mode)", () => {
    expect(resolveMaxFileSizeBytes(50, null)).toBe(50 * 1024 * 1024);
  });
});
