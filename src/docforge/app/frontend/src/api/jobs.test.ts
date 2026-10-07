// ====== Code Summary ======
// Job kind labelling: the collection-level rebuild_index job (document_id null) is named by its kind.

import { describe, expect, it } from "vitest";
import { jobDisplayName, jobKindLabel } from "./jobs";

describe("job kind labels", () => {
  it("labels the collection-level rebuild_index job", () => {
    expect(jobKindLabel("rebuild_index")).toBe("index rebuild");
  });

  it("names a document-less rebuild job by its kind, never 'untitled document'", () => {
    const job = { kind: "rebuild_index", display_title: null, document_title: null, document_filename: null };
    expect(jobDisplayName(job)).toBe("index rebuild");
  });

  it("keeps naming a document job by its document", () => {
    const job = { kind: "ingest", display_title: null, document_title: null, document_filename: "a.md" };
    expect(jobDisplayName(job)).toBe("a.md");
  });
});
