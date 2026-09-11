// ====== Code Summary ======
// Render smoke-test for the business-audience relabel: the store legend/header must lead with the
// business-facing name ("Source files"/"Metadata"/"Search index"), while the raw product name
// (S3/PostgreSQL/Qdrant) only rides along inside each store's collapsed-by-default "Breakdown"
// disclosure — never as the primary label. Repro for the audit fix, not a general disclosure test.

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CollectionStorage } from "../../../api/collections";
import { StorageFootprintPanel } from "./StorageFootprintPanel";

vi.mock("../../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/collections")>()),
  fetchCollectionStorage: vi.fn(),
}));

const { fetchCollectionStorage } = await import("../../../api/collections");

const storage: CollectionStorage = {
  collection_id: "col-1",
  s3: { original_bytes: 2048, rendered_bytes: 0, total_bytes: 2048, physical_unique_bytes: 2048, estimated: false },
  postgres: { documents_bytes: 512, ir_blocks_bytes: 256, enrichment_bytes: 0, chunks_bytes: 128, metadata_bytes: 64, observability_bytes: 0, total_bytes: 960, estimated: true },
  qdrant: { points: 4, dense_bytes: 4096, sparse_bytes: 0, payload_bytes: 128, total_bytes: 4224, estimated: false },
  grand_total_bytes: 7232,
  documents: [
    {
      document_id: "doc-1",
      filename: "report.pdf",
      s3: { original_bytes: 2048, rendered_bytes: 0, total_bytes: 2048, physical_unique_bytes: 2048, estimated: false },
      postgres: { documents_bytes: 512, ir_blocks_bytes: 256, enrichment_bytes: 0, chunks_bytes: 128, metadata_bytes: 64, observability_bytes: 0, total_bytes: 960, estimated: true },
      qdrant: { points: 4, dense_bytes: 4096, sparse_bytes: 0, payload_bytes: 128, total_bytes: 4224, estimated: false },
      total_bytes: 7232,
    },
  ],
};

describe("StorageFootprintPanel", () => {
  it("leads with business-facing store names and keeps the raw product name behind a closed disclosure", async () => {
    vi.mocked(fetchCollectionStorage).mockResolvedValue(storage);
    const { container } = render(<StorageFootprintPanel collectionId="col-1" onNavigate={vi.fn()} />);

    await waitFor(() => expect(screen.getAllByText("Source files").length).toBeGreaterThan(0));
    expect(screen.getAllByText("Metadata").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Search index").length).toBeGreaterThan(0);

    // Every per-store "Breakdown" disclosure — where the raw store name lives — starts collapsed.
    const disclosures = container.querySelectorAll("details");
    expect(disclosures.length).toBeGreaterThan(0);
    disclosures.forEach((details) => expect(details.open).toBe(false));

    // The raw product name is present in the document (native <details> content isn't removed from
    // the DOM when closed) but only inside that collapsed disclosure, not as a standalone headline.
    const technicalNames = ["S3", "PostgreSQL", "Qdrant"];
    technicalNames.forEach((name) => {
      const hit = screen.getByText(name);
      expect(hit.closest("details")).not.toBeNull();
    });
  });
});
