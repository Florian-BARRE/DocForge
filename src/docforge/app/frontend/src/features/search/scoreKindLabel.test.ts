// ====== Code Summary ======
// Pins the score_kind captions, including the raw single-vector kinds (no fusion ran).

import { describe, expect, it } from "vitest";
import { scoreKindLabel } from "./scoreKindLabel";

describe("scoreKindLabel", () => {
  it("captions the fusion, rerank and raw single-vector kinds", () => {
    expect(scoreKindLabel("rrf_fusion")).toBe("hybrid RRF");
    expect(scoreKindLabel("cross_encoder_rerank")).toBe("cross-encoder rerank");
    expect(scoreKindLabel("raw_dense")).toBe("dense similarity");
    expect(scoreKindLabel("raw_sparse")).toBe("lexical score");
  });

  it("shows an unknown kind verbatim and nothing for an absent one", () => {
    expect(scoreKindLabel("future_kind")).toBe("future_kind");
    expect(scoreKindLabel(undefined)).toBeNull();
  });
});
