// ====== Code Summary ======
// Render smoke-test for SystemMetadataPanel: a fully-populated DocumentDetail + pages array renders
// every group (Identity/Source/Parsed/Content/Status) without throwing, including the derived
// pages-scanned/other-languages summary; a pre-parse document (null language/page_count/pages) must
// render its "—"/"undetected" fallbacks instead of throwing — the exact class of bug the frontend
// render-smoke gate exists to catch.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DocumentDetail, PageInfo } from "../../../api/explorer";
import { SystemMetadataPanel } from "./SystemMetadataPanel";

const baseDocument: DocumentDetail = {
  id: "doc-1",
  collection_id: "col-1",
  filename: "report.pdf",
  format: "pdf",
  mime_type: "application/pdf",
  file_size: 2_500_000,
  page_count: 4,
  language: "en",
  title: "Quarterly Report",
  source_kind: "mixed",
  status: "done",
  source_hash: "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
  pdf_blob_hash: "f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1f6e5d4c3b2a1",
  simhash: "1234567890abcdef",
  pipeline_version: "v3",
  created_at: "2026-02-01T00:00:00Z",
  enabled: true,
  chunk_count: 42,
  warning_reason: null,
  metadata: [],
};

function page(n: number, scanned: boolean, language: string | null): PageInfo {
  return { page_number: n, width: 800, height: 1000, is_scanned: scanned, language, render_blob_hash: `hash-${n}` };
}

describe("SystemMetadataPanel", () => {
  it("renders every group for a fully-populated document + pages without throwing", () => {
    const pages = [page(0, false, "en"), page(1, true, "fr"), page(2, true, "en")];

    expect(() => render(<SystemMetadataPanel document={baseDocument} pages={pages} />)).not.toThrow();

    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("Source")).toBeInTheDocument();
    expect(screen.getByText("Parsed")).toBeInTheDocument();
    expect(screen.getByText("Content")).toBeInTheDocument();
    // "Status" appears twice — the group heading and, inside it, the fact label above the status
    // chip (see MetaGroup + FactLabel) — so this asserts both are present instead of picking one.
    expect(screen.getAllByText("Status")).toHaveLength(2);

    // Page-derived facts, computed purely from the already-loaded pages array.
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    expect(screen.getByText(/Other page languages: fr/)).toBeInTheDocument();
  });

  it("tolerates a pre-parse document with null language/page_count and no pages yet", () => {
    const prePassDocument: DocumentDetail = {
      ...baseDocument,
      page_count: null,
      language: null,
      pdf_blob_hash: null,
      simhash: null,
      chunk_count: null,
      warning_reason: "No pages parsed yet",
    };

    expect(() => render(<SystemMetadataPanel document={prePassDocument} pages={null} />)).not.toThrow();

    expect(screen.getByText("undetected")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("No pages parsed yet")).toBeInTheDocument();
  });
});
