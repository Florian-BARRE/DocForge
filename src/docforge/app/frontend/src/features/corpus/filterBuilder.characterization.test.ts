// ====== Code Summary ======
// Characterization (safety net) of corpus/filterBuilder.ts: records TODAY's translation from the
// grid's per-column filter state to the API `DocumentFilter` JSON, for every filter kind on both a
// base column and a metadata (`meta:`) column. Pins the "empty value emits nothing" rule, trimming,
// the gte/lte split of range kinds into two metadata entries, and the entry order. A diff here
// changes the query body the backend receives.

// ====== Third-Party Library Imports ======
import { describe, expect, it } from "vitest";

// ====== Local Project Imports ======
import { buildDocumentFilter } from "./filterBuilder";
import type { ColumnFiltersState } from "./types";

/** The filter as it goes over the wire (undefined keys dropped). */
function wire(state: ColumnFiltersState): unknown {
  return JSON.parse(JSON.stringify(buildDocumentFilter(state)));
}

describe("buildDocumentFilter — base columns", () => {
  it("is {} for an empty state", () => {
    expect(wire({})).toEqual({});
  });

  it("text on filename and title becomes {contains}, trimmed", () => {
    expect(
      wire({ filename: { kind: "text", contains: "  inv  " }, title: { kind: "text", contains: "q3" } }),
    ).toEqual({ filename: { contains: "inv" }, title: { contains: "q3" } });
  });

  it("text on an unmapped base column emits nothing", () => {
    expect(wire({ author: { kind: "text", contains: "x" } })).toEqual({});
  });

  it("enumMulti on status and format becomes the value arrays", () => {
    expect(
      wire({ status: { kind: "enumMulti", values: ["ready", "failed"] }, format: { kind: "enumMulti", values: ["pdf"] } }),
    ).toEqual({ status: ["ready", "failed"], format: ["pdf"] });
  });

  it("enumMulti on an unmapped base column emits nothing", () => {
    expect(wire({ language: { kind: "enumMulti", values: ["fr"] } })).toEqual({});
  });

  it("listIn on language becomes the value array; on other base columns it emits nothing", () => {
    expect(wire({ language: { kind: "listIn", values: ["fr", "en"] } })).toEqual({ language: ["fr", "en"] });
    expect(wire({ status: { kind: "listIn", values: ["ready"] } })).toEqual({});
  });

  it("bool on enabled becomes true/false; null emits nothing; other columns emit nothing", () => {
    expect(wire({ enabled: { kind: "bool", value: true } })).toEqual({ enabled: true });
    expect(wire({ enabled: { kind: "bool", value: false } })).toEqual({ enabled: false });
    expect(wire({ enabled: { kind: "bool", value: null } })).toEqual({});
    expect(wire({ other: { kind: "bool", value: true } })).toEqual({});
  });

  it("numberRange on file_size / page_count becomes {gte, lte} with a missing bound dropped", () => {
    expect(
      wire({
        file_size: { kind: "numberRange", gte: "10", lte: "2000" },
        page_count: { kind: "numberRange", gte: "", lte: " 5 " },
      }),
    ).toEqual({ file_size: { gte: 10, lte: 2000 }, page_count: { lte: 5 } });
  });

  it("numberRange ignores an unparsable bound and emits nothing when both are empty or invalid", () => {
    expect(wire({ file_size: { kind: "numberRange", gte: "abc", lte: "7" } })).toEqual({ file_size: { lte: 7 } });
    expect(wire({ file_size: { kind: "numberRange", gte: "abc", lte: "" } })).toEqual({});
    expect(wire({ file_size: { kind: "numberRange", gte: "", lte: "" } })).toEqual({});
  });

  it("numberRange keeps a zero bound (0 is a real value)", () => {
    expect(wire({ file_size: { kind: "numberRange", gte: "0", lte: "" } })).toEqual({ file_size: { gte: 0 } });
  });

  it("numberRange on an unmapped base column emits nothing", () => {
    expect(wire({ other: { kind: "numberRange", gte: "1", lte: "2" } })).toEqual({});
  });

  it("dateRange on created_at becomes ISO strings, a missing or invalid bound dropped", () => {
    expect(wire({ created_at: { kind: "dateRange", gte: "2026-01-15", lte: "2026-02-01T10:30:00Z" } })).toEqual({
      created_at: { gte: "2026-01-15T00:00:00.000Z", lte: "2026-02-01T10:30:00.000Z" },
    });
    expect(wire({ created_at: { kind: "dateRange", gte: "2026-01-15", lte: "not a date" } })).toEqual({
      created_at: { gte: "2026-01-15T00:00:00.000Z" },
    });
    expect(wire({ created_at: { kind: "dateRange", gte: "", lte: "nope" } })).toEqual({});
  });

  it("dateRange on an unmapped base column emits nothing", () => {
    expect(wire({ updated_at: { kind: "dateRange", gte: "2026-01-15", lte: "" } })).toEqual({});
  });

  it("empty text and empty lists emit nothing", () => {
    expect(
      wire({
        filename: { kind: "text", contains: "   " },
        status: { kind: "enumMulti", values: [] },
        language: { kind: "listIn", values: [] },
      }),
    ).toEqual({});
  });
});

describe("buildDocumentFilter — metadata columns", () => {
  it("text -> contains entry (trimmed)", () => {
    expect(wire({ "meta:author": { kind: "text", contains: " ada " } })).toEqual({
      metadata: [{ field: "author", op: "contains", value: "ada" }],
    });
  });

  it("enumMulti and listIn -> `in` entries", () => {
    expect(
      wire({ "meta:kind": { kind: "enumMulti", values: ["a", "b"] }, "meta:tags": { kind: "listIn", values: ["x"] } }),
    ).toEqual({
      metadata: [
        { field: "kind", op: "in", value: ["a", "b"] },
        { field: "tags", op: "in", value: ["x"] },
      ],
    });
  });

  it("bool -> eq entry (false kept, null dropped)", () => {
    expect(wire({ "meta:flag": { kind: "bool", value: false }, "meta:other": { kind: "bool", value: null } })).toEqual({
      metadata: [{ field: "flag", op: "eq", value: false }],
    });
  });

  it("numberRange splits into a gte entry then an lte entry", () => {
    expect(wire({ "meta:score": { kind: "numberRange", gte: "1", lte: "9" } })).toEqual({
      metadata: [
        { field: "score", op: "gte", value: 1 },
        { field: "score", op: "lte", value: 9 },
      ],
    });
    expect(wire({ "meta:score": { kind: "numberRange", gte: "", lte: "9" } })).toEqual({
      metadata: [{ field: "score", op: "lte", value: 9 }],
    });
  });

  it("dateRange splits into gte/lte entries with ISO values", () => {
    expect(wire({ "meta:due": { kind: "dateRange", gte: "2026-03-01", lte: "2026-03-31" } })).toEqual({
      metadata: [
        { field: "due", op: "gte", value: "2026-03-01T00:00:00.000Z" },
        { field: "due", op: "lte", value: "2026-03-31T00:00:00.000Z" },
      ],
    });
  });

  it("empty metadata values emit no `metadata` key at all", () => {
    expect(
      wire({
        "meta:a": { kind: "text", contains: "" },
        "meta:b": { kind: "enumMulti", values: [] },
        "meta:c": { kind: "numberRange", gte: "", lte: "" },
      }),
    ).toEqual({});
  });

  it("metadata entries follow the state's key order, after being collected across kinds", () => {
    const filter = wire({
      "meta:b": { kind: "text", contains: "y" },
      filename: { kind: "text", contains: "f" },
      "meta:a": { kind: "bool", value: true },
    }) as { filename: unknown; metadata: Array<{ field: string }> };
    expect(filter.filename).toEqual({ contains: "f" });
    expect(filter.metadata.map((m) => m.field)).toEqual(["b", "a"]);
  });
});

describe("buildDocumentFilter — combined", () => {
  it("builds one AND-combined filter from base and metadata columns", () => {
    expect(
      wire({
        filename: { kind: "text", contains: "report" },
        status: { kind: "enumMulti", values: ["ready"] },
        enabled: { kind: "bool", value: true },
        file_size: { kind: "numberRange", gte: "1", lte: "" },
        "meta:team": { kind: "text", contains: "core" },
      }),
    ).toEqual({
      filename: { contains: "report" },
      status: ["ready"],
      enabled: true,
      file_size: { gte: 1 },
      metadata: [{ field: "team", op: "contains", value: "core" }],
    });
  });
});
