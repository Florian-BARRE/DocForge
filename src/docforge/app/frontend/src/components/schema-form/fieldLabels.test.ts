// ====== Code Summary ======
// Regression test for round-4 T2: `isSecretFieldName` must mask real credentials only, never a
// field whose name merely CONTAINS a secret-sounding substring — the exact bug that masked the
// Chunk step's `tokenizer_encoding` (a public tiktoken encoding name, e.g. `cl100k_base`) as a
// password field.

import { describe, expect, it } from "vitest";
import { isSecretFieldName } from "./fieldLabels";

describe("isSecretFieldName — exact-leaf allowlist, not substring matching", () => {
  it("masks every known real secret leaf (mirrors backend SECRET_FIELDS)", () => {
    expect(isSecretFieldName("api_key")).toBe(true);
    expect(isSecretFieldName("password")).toBe(true);
  });

  it("masks a prefixed variant of a real secret leaf", () => {
    expect(isSecretFieldName("basic_auth_password")).toBe(true);
    expect(isSecretFieldName("gotenberg_api_key")).toBe(true);
  });

  it("does NOT mask tokenizer_encoding (public tiktoken id, not a secret)", () => {
    expect(isSecretFieldName("tokenizer_encoding")).toBe(false);
  });

  it("does NOT mask other fields that merely contain a secret-sounding substring", () => {
    expect(isSecretFieldName("token_count")).toBe(false);
    expect(isSecretFieldName("max_tokens")).toBe(false);
    expect(isSecretFieldName("secret_score_label")).toBe(false);
  });
});
