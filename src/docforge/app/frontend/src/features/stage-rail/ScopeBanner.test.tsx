// ====== Code Summary ======
// Render smoke-test for IngestScopeBanner: it always renders its one-line orientation copy.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IngestScopeBanner } from "./ScopeBanner";

describe("IngestScopeBanner", () => {
  it("renders the ingest-scope reminder", () => {
    render(<IngestScopeBanner />);
    expect(screen.getByText("Runs once when a document is ingested.")).toBeInTheDocument();
  });
});
