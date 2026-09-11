// ====== Code Summary ======
// Covers the exact raw `str(pydantic.ValidationError)` shape the naive-user GUI campaign flagged
// (model name, `[type=...]` bracket, errors.pydantic.dev link, shown verbatim in the search
// pipeline's field validation) — asserts it collapses to a clean `field: message` issue.

import { describe, expect, it } from "vitest";
import { humanizePydanticError, issuesFromBuildError } from "./http";

const RAW_PYDANTIC_ERROR = `1 validation error for QueryNormalizeConfig
candidate_multiplier
  Input should be greater than 0 [type=greater_than, input_value=-5, input_type=int]
    For further information visit https://errors.pydantic.dev/2.13/v/greater_than`;

describe("humanizePydanticError", () => {
  it("extracts a clean field: message issue, dropping the model name/bracket/link", () => {
    const issues = humanizePydanticError(RAW_PYDANTIC_ERROR);
    expect(issues).toEqual([{ location: "candidate_multiplier", message: "Input should be greater than 0" }]);
  });

  it("returns [] for a plain string that isn't a pydantic dump", () => {
    expect(humanizePydanticError("duplicate_unique_node: embed")).toEqual([]);
  });

  it("still extracts the issue when the write boundary wraps it in its own prefix prose", () => {
    // The exact shape PipelineBlobValidator/BuildError produce at the 422 write boundary — the
    // iteration-2 regression: the leading prefix used to defeat the anchored header match, leaving
    // the raw pydantic dump (model name + [type=...] + errors.pydantic.dev link) in the save banner.
    const wrapped = `Pipeline blob cannot be built: ${RAW_PYDANTIC_ERROR}`;
    expect(humanizePydanticError(wrapped)).toEqual([
      { location: "candidate_multiplier", message: "Input should be greater than 0" },
    ]);
  });
});

describe("issuesFromBuildError", () => {
  it("ties the humanized issue's location to the offending field", () => {
    expect(issuesFromBuildError(RAW_PYDANTIC_ERROR)).toEqual([
      { code: "build_error", location: "candidate_multiplier", message: "Input should be greater than 0" },
    ]);
  });

  it("falls back to one generic 'blob' issue for a non-pydantic build error", () => {
    expect(issuesFromBuildError("duplicate_unique_node: embed")).toEqual([
      { code: "build_error", location: "blob", message: "duplicate_unique_node: embed" },
    ]);
  });
});
