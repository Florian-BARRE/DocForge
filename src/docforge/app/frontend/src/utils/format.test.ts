// ====== Code Summary ======
// Shared formatters: byte-size thresholds/rounding and the null date placeholder.

import { describe, expect, it } from "vitest";
import { formatBytes, formatDateTime } from "./format";

describe("formatBytes", () => {
  it("keeps raw bytes below 1 KiB", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
  });

  it("scales through binary units with one decimal", () => {
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1024 * 1024)).toBe("1.0 MB");
    expect(formatBytes(1024 ** 3)).toBe("1.0 GB");
  });

  it("stays in TB for very large sizes", () => {
    expect(formatBytes(1024 ** 4 * 2048)).toBe("2048.0 TB");
  });
});

describe("formatDateTime", () => {
  it("renders an em dash for null", () => {
    expect(formatDateTime(null)).toBe("—");
  });

  it("renders a parsed timestamp locally", () => {
    const iso = "2026-01-02T03:04:05Z";
    expect(formatDateTime(iso)).toBe(new Date(iso).toLocaleString());
  });
});
