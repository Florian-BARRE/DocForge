// ====== Code Summary ======
// Structure guard of the api facades split out of the former `collections.ts` / `jobs.ts`: every
// module stays within 400 lines and each folder's index keeps re-exporting the public names the
// callers import from "api/collections" and "api/jobs".

import { describe, expect, it } from "vitest";
import * as collections from "./collections";
import * as jobs from "./jobs";

const MAX_LINES = 400;
const sources = import.meta.glob("./{collections,jobs}/*.ts", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

describe("api module size", () => {
  it("finds the split modules", () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(10);
  });

  it.each(Object.entries(sources))("%s stays within the line budget", (_path, source) => {
    expect(source.split("\n").length).toBeLessThanOrEqual(MAX_LINES);
  });
});

describe("api facades keep their public surface", () => {
  it("re-exports the collections runtime names", () => {
    for (const name of [
      "FIELD_TYPES", "FIELD_ORIGINS", "FIELD_SCOPES", "FIELD_DESCRIPTION_MAX_LENGTH",
      "listCollections", "getCollection", "createCollection", "updateCollection", "deleteCollection",
      "rebuildCollectionIndex", "fetchCollectionContractSchema", "getCollectionHealth", "fetchCollectionStorage",
      "reingestCollection", "estimateCollectionCost", "purgeCollectionTracePayloads",
    ]) {
      expect(collections, name).toHaveProperty(name);
    }
  });

  it("re-exports the jobs runtime names, streamJobEvents included", () => {
    for (const name of [
      "jobKindLabel", "isIngestJob", "jobDisplayName", "listJobsPage", "listJobs", "getJob", "cancelJob",
      "getJobTrace", "getEventPayload", "getStageDurations", "getCollectionCost", "getWorkersLive",
      "getQueueDepth", "getFailureBreakdown", "getNewFailures", "getJobTimeseries", "streamJobEvents",
    ]) {
      expect(jobs, name).toHaveProperty(name);
    }
  });
});
