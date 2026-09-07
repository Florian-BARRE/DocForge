// ====== Code Summary ======
// "System metadata" — everything DocForge derives about a document, gathered in one place and
// grouped into small subsections (Identity / Source / Parsed / Content / Status) instead of one
// flat wall of facts. Reuses the DocumentDetail already loaded by the overview page; the per-page
// scan/language summary additionally consumes the Pages tab's cached list when available (warmed
// for the overview tab too — see useDocumentTabs) and degrades to "—" before it lands, never
// fetching the heavy IR just for a count.

import type { DocumentDetail, PageInfo } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";
import { theme } from "../../../theme";
import { DocumentStatusChip } from "../DocumentStatusChip";
import { formatBytes, formatDateTime } from "../format";
import { Fact, FactLabel } from "./Fact";
import { MetaGroup } from "./MetaGroup";
import { summarizePageScans } from "./pageScanSummary";

interface SystemMetadataPanelProps {
  document: DocumentDetail;
  /** The document's page list, once loaded — null while the overview tab hasn't warmed it yet, or
   *  on a pages-fetch error; the panel degrades to "—" for the page-derived facts either way. */
  pages: PageInfo[] | null;
}

export function SystemMetadataPanel({ document, pages }: SystemMetadataPanelProps) {
  const pageSummary = pages && pages.length ? summarizePageScans(pages, document.language) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <MetaGroup title="Identity">
        <Fact label="Document ID" value={document.id} mono />
        <Fact label="Source hash" value={document.source_hash} mono hint="sha256 of the original uploaded file" />
        <Fact
          label="PDF blob"
          value={document.pdf_blob_hash ?? "—"}
          mono
          hint="sha256 of the canonical PDF render used for page previews (distinct from the source hash for non-PDF uploads)"
        />
        <Fact label="Simhash" value={document.simhash ?? "—"} mono hint="near-duplicate fingerprint" />
      </MetaGroup>

      <MetaGroup title="Source">
        <Fact label="Filename" value={document.filename} />
        <Fact label="Format" value={document.format} />
        <Fact label="MIME type" value={document.mime_type} mono />
        <Fact label="File size" value={formatBytes(document.file_size)} />
        <Fact label="Source kind" value={humanizeEnumOption(document.source_kind)} />
        <Fact label="Admitted" value={formatDateTime(document.created_at)} />
      </MetaGroup>

      <MetaGroup title="Parsed">
        <Fact label="Title" value={document.title || "—"} />
        <Fact label="Page count" value={document.page_count === null ? "—" : String(document.page_count)} mono />
        <Fact label="Language" value={document.language || "undetected"} mono />
        <Fact label="Pipeline version" value={document.pipeline_version} mono />
      </MetaGroup>

      <MetaGroup title="Content">
        <Fact label="Chunks" value={document.chunk_count === null ? "—" : String(document.chunk_count)} mono />
        <Fact
          label="Pages scanned"
          value={pageSummary ? `${pageSummary.scanned} of ${pageSummary.total}` : "—"}
          mono
          hint={pageSummary && pageSummary.otherLanguages.length ? `Other page languages: ${pageSummary.otherLanguages.join(", ")}` : undefined}
        />
      </MetaGroup>

      <MetaGroup title="Status">
        <div>
          <FactLabel>Status</FactLabel>
          <DocumentStatusChip status={document.status} hasWarning={!!document.warning_reason} />
        </div>
        <Fact label="Searchable" value={document.enabled ? "enabled" : "disabled"} />
        {document.warning_reason && (
          <div>
            <FactLabel>Warning</FactLabel>
            <Chip tone="warn" title={document.warning_reason}>
              {document.warning_reason}
            </Chip>
          </div>
        )}
      </MetaGroup>
    </div>
  );
}
