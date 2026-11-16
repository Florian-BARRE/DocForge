// ====== Code Summary ======
// Covers the exact chained-exception shape the naive-user GUI campaign flagged as raw/scary
// ("PipelineRunError: pipeline run failed: admit (admission): ValueError: Upload rejected: file is
// empty" rendered verbatim on Home/Jobs) — asserts only the useful tail survives.

import { describe, expect, it } from "vitest";
import { humanizeJobError } from "./jobErrorHumanize";

describe("humanizeJobError", () => {
  it("keeps only the tail after the last exception-class prefix", () => {
    expect(
      humanizeJobError("PipelineRunError: pipeline run failed: admit (admission): ValueError: Upload rejected: file is empty"),
    ).toBe("Upload rejected: file is empty");
  });

  it("leaves a plain message (no exception-class prefix) unchanged", () => {
    expect(humanizeJobError("Upload rejected: file is empty")).toBe("Upload rejected: file is empty");
  });

  it("still strips a single-level exception prefix", () => {
    expect(humanizeJobError("ConnectionError: could not reach https://host:8080")).toBe(
      "could not reach https://host:8080",
    );
  });
});
