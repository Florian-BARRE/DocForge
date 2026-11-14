// ====== Code Summary ======
// Characterization (safety net) of shell/urlSync.ts: records TODAY's View <-> hash mapping so the
// route-table refactor (R-34) cannot move a URL. Pins the serialize golden and the
// parse(serialize(v)) == v round-trip for EVERY View variant (with and without each optional
// health / stage / section / tab), the lenient parse of legacy hashes, id encoding, and the
// fall-back to the overview for anything unknown. A diff here changes users' bookmarks.

// ====== Third-Party Library Imports ======
import { describe, expect, it } from "vitest";

// ====== Local Project Imports ======
import { parseViewFromHash, serializeViewToHash } from "./urlSync";
import type { View } from "./view";

const OVERVIEW: View = { name: "overview" };

/** Every View variant (and each optional-field value) with its canonical hash path. */
const CANONICAL: Array<[View, string]> = [
  [{ name: "overview" }, "/overview"],
  [{ name: "activity" }, "/activity"],
  [{ name: "activity", tab: "failures" }, "/activity/failures"],
  [{ name: "activity", tab: "trends" }, "/activity/trends"],
  [{ name: "collections" }, "/collections"],
  [{ name: "collections", health: "attention" }, "/collections/filter/attention"],
  [{ name: "collections", health: "operational" }, "/collections/filter/operational"],
  [{ name: "collections", health: "empty" }, "/collections/filter/empty"],
  [{ name: "new-collection" }, "/collections/new"],
  [{ name: "import-collection" }, "/collections/import"],
  [{ name: "collection", collectionId: "c1" }, "/collections/c1"],
  [{ name: "collection-documents", collectionId: "c1" }, "/collections/c1/documents"],
  [{ name: "collection-search", collectionId: "c1" }, "/collections/c1/search"],
  [{ name: "collection-pipelines", collectionId: "c1", stage: "ingestion" }, "/collections/c1/pipelines/ingestion"],
  [{ name: "collection-pipelines", collectionId: "c1", stage: "search" }, "/collections/c1/pipelines/search"],
  [{ name: "collection-schema", collectionId: "c1" }, "/collections/c1/schema"],
  [{ name: "collection-activity", collectionId: "c1" }, "/collections/c1/activity"],
  [{ name: "collection-settings", collectionId: "c1" }, "/collections/c1/settings"],
  [{ name: "collection-settings", collectionId: "c1", section: "aliases" }, "/collections/c1/settings/aliases"],
  [{ name: "collection-settings", collectionId: "c1", section: "history" }, "/collections/c1/settings/history"],
  [{ name: "collection-settings", collectionId: "c1", section: "transfer" }, "/collections/c1/settings/transfer"],
  [{ name: "document", collectionId: "c1", documentId: "d1" }, "/collections/c1/documents/d1"],
  [{ name: "job", collectionId: "c1", jobId: "j1" }, "/collections/c1/jobs/j1"],
  [{ name: "fleet" }, "/fleet"],
  [{ name: "settings" }, "/settings"],
  [{ name: "settings", section: "audit" }, "/settings/audit"],
  [{ name: "settings", section: "deployment" }, "/settings/deployment"],
  [{ name: "api-key", keyId: "k1" }, "/settings/keys/k1"],
];

describe("serializeViewToHash — canonical goldens", () => {
  it.each(CANONICAL)("%j -> %s", (view, hash) => {
    expect(serializeViewToHash(view)).toBe(hash);
  });

  it("writes the bare path for the default optional values (tab jobs, stage absent, section general/keys)", () => {
    expect(serializeViewToHash({ name: "activity", tab: "jobs" })).toBe("/activity");
    expect(serializeViewToHash({ name: "collection-pipelines", collectionId: "c1" })).toBe("/collections/c1/pipelines/ingestion");
    expect(serializeViewToHash({ name: "collection-settings", collectionId: "c1", section: "general" })).toBe("/collections/c1/settings");
    expect(serializeViewToHash({ name: "settings", section: "keys" })).toBe("/settings");
  });

  it("URI-encodes every id segment", () => {
    expect(serializeViewToHash({ name: "document", collectionId: "a/b c", documentId: "d?#1" })).toBe(
      "/collections/a%2Fb%20c/documents/d%3F%231",
    );
    expect(serializeViewToHash({ name: "api-key", keyId: "k é" })).toBe("/settings/keys/k%20%C3%A9");
  });
});

describe("parseViewFromHash — round trip", () => {
  it.each(CANONICAL)("parse(serialize(%j)) returns the same view", (view) => {
    expect(parseViewFromHash(serializeViewToHash(view))).toEqual(view);
    expect(parseViewFromHash(`#${serializeViewToHash(view)}`)).toEqual(view);
  });

  it("round-trips ids that need URI encoding", () => {
    const views: View[] = [
      { name: "collection", collectionId: "a/b c" },
      { name: "document", collectionId: "a/b c", documentId: "d?#1" },
      { name: "job", collectionId: "é", jobId: "j 1" },
      { name: "api-key", keyId: "k é/1" },
    ];
    for (const view of views) expect(parseViewFromHash(serializeViewToHash(view))).toEqual(view);
  });

  it("an explicit default value parses back to the ABSENT optional (not the explicit default)", () => {
    expect(parseViewFromHash(serializeViewToHash({ name: "activity", tab: "jobs" }))).toEqual({ name: "activity" });
    expect(
      parseViewFromHash(serializeViewToHash({ name: "collection-settings", collectionId: "c1", section: "general" })),
    ).toEqual({ name: "collection-settings", collectionId: "c1" });
    expect(parseViewFromHash(serializeViewToHash({ name: "settings", section: "keys" }))).toEqual({ name: "settings" });
    expect(parseViewFromHash(serializeViewToHash({ name: "collection-pipelines", collectionId: "c1" }))).toEqual({
      name: "collection-pipelines",
      collectionId: "c1",
      stage: "ingestion",
    });
  });
});

describe("parseViewFromHash — legacy hashes (parsed, never serialized)", () => {
  it.each<[string, View]>([
    ["#/home", { name: "overview" }],
    ["#/jobs", { name: "activity" }],
    ["#/jobs/failures", { name: "activity", tab: "failures" }],
    ["#/jobs/trends", { name: "activity", tab: "trends" }],
    ["#/jobs/whatever", { name: "activity" }],
    ["#/workers", { name: "fleet" }],
    ["#/api-keys", { name: "settings" }],
    ["#/api-keys/k1", { name: "api-key", keyId: "k1" }],
    ["#/collections/c1/metadata", { name: "collection-schema", collectionId: "c1" }],
    ["#/collections/c1/edit", { name: "collection-settings", collectionId: "c1" }],
    ["#/collections/c1/pipeline", { name: "collection-pipelines", collectionId: "c1", stage: "ingestion" }],
    ["#/collections/c1/search-pipeline", { name: "collection-pipelines", collectionId: "c1", stage: "search" }],
    ["#/collections/c1/jobs", { name: "collection-activity", collectionId: "c1" }],
    ["#/collections/c1/activity/j9", { name: "job", collectionId: "c1", jobId: "j9" }],
  ])("%s", (hash, view) => {
    expect(parseViewFromHash(hash)).toEqual(view);
  });

  it("never serializes a legacy path back", () => {
    for (const hash of ["#/home", "#/jobs", "#/workers", "#/api-keys", "#/collections/c1/edit", "#/collections/c1/pipeline"]) {
      expect(serializeViewToHash(parseViewFromHash(hash))).not.toBe(hash.slice(1));
    }
  });
});

describe("parseViewFromHash — unknown or malformed hashes", () => {
  it.each(["", "#", "#/", "#//", "#/nope", "#/nope/deeper", "#/collection/c1", "#/COLLECTIONS"])(
    "%j falls back to the overview",
    (hash) => {
      expect(parseViewFromHash(hash)).toEqual(OVERVIEW);
    },
  );

  it.each([
    ["#/overview/extra", OVERVIEW],
    ["#/home/extra", OVERVIEW],
    ["#/fleet/extra", OVERVIEW],
    ["#/workers/extra", OVERVIEW],
    ["#/api-keys/a/b", OVERVIEW],
  ] as Array<[string, View]>)("%s falls back to the overview", (hash, view) => {
    expect(parseViewFromHash(hash)).toEqual(view);
  });

  it("empty path segments are dropped before matching, so '//' collapses", () => {
    expect(parseViewFromHash("#/collections//documents")).toEqual({ name: "collection", collectionId: "documents" });
    expect(parseViewFromHash("#//fleet//")).toEqual({ name: "fleet" });
  });

  it("an unknown collections filter keeps the collections list unfiltered", () => {
    expect(parseViewFromHash("#/collections/filter/bogus")).toEqual({ name: "collections" });
  });

  it("an unknown collection tab lands on the collection root", () => {
    expect(parseViewFromHash("#/collections/c1/bogus")).toEqual({ name: "collection", collectionId: "c1" });
  });

  it("an unknown settings sub-path lands on the plain deployment settings", () => {
    expect(parseViewFromHash("#/settings/bogus")).toEqual({ name: "settings" });
    expect(parseViewFromHash("#/settings/audit/extra")).toEqual({ name: "settings" });
    expect(parseViewFromHash("#/settings/keys")).toEqual({ name: "settings" });
  });

  it("an unknown pipelines stage defaults to ingestion", () => {
    expect(parseViewFromHash("#/collections/c1/pipelines/bogus")).toEqual({
      name: "collection-pipelines",
      collectionId: "c1",
      stage: "ingestion",
    });
  });

  it("a document id is read from the third segment, extra segments are ignored", () => {
    expect(parseViewFromHash("#/collections/c1/documents/d1/extra")).toEqual({
      name: "document",
      collectionId: "c1",
      documentId: "d1",
    });
  });

  it("decodes percent-encoded segments", () => {
    expect(parseViewFromHash("#/collections/a%2Fb/documents/d%201")).toEqual({
      name: "document",
      collectionId: "a/b",
      documentId: "d 1",
    });
  });

  it("accepts a hash without the leading '#'", () => {
    expect(parseViewFromHash("/fleet")).toEqual({ name: "fleet" });
  });

  it("throws on a malformed percent-escape (decodeURIComponent is not guarded)", () => {
    expect(() => parseViewFromHash("#/collections/%E0%A4%A")).toThrow(URIError);
  });
});
