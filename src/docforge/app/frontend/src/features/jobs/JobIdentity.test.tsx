// ====== Code Summary ======
// The job identity block tags a stage-replay run ("replay from <stage>") and stays silent for a full run.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobStatus } from "../../api/jobs";
import { JobIdentity } from "./JobIdentity";

const base = {
  job_id: "job-12345678", kind: "ingest", document_id: "doc-12345678", document_filename: "a.pdf", document_title: null,
  collection_name: "col", current_stage: null,
} as JobStatus;

describe("JobIdentity replay tag", () => {
  it("shows the replay stage when replay_from is set", () => {
    render(<JobIdentity job={{ ...base, replay_from: "embed" }} />);
    expect(screen.getByText(/replay from/)).toBeInTheDocument();
    expect(screen.getByText("embed")).toBeInTheDocument();
  });

  it("shows nothing for a full run", () => {
    render(<JobIdentity job={{ ...base, replay_from: null }} />);
    expect(screen.queryByText(/replay from/)).not.toBeInTheDocument();
  });
});
