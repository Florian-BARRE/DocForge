// ====== Code Summary ======
// The document's own parse-time facts as a compact label/value grid — everything DocumentDetail
// carries besides its metadata list and the fields already shown in the page header.

import type { DocumentDetail } from "../../../api/explorer";
import { theme } from "../../../theme";
import { formatDateTime } from "../format";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{label}</div>
      <div style={{ fontSize: theme.font.size.s, wordBreak: "break-all" }}>{value}</div>
    </div>
  );
}

export function FactsGrid({ document }: { document: DocumentDetail }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: theme.space.m }}>
      <Fact label="Format" value={document.format} />
      <Fact label="MIME type" value={document.mime_type} />
      <Fact label="Source kind" value={document.source_kind} />
      <Fact label="Title" value={document.title || "—"} />
      <Fact label="Language" value={document.language || "—"} />
      <Fact label="Pipeline version" value={document.pipeline_version} />
      <Fact label="Admitted" value={formatDateTime(document.created_at)} />
      <Fact label="Source hash" value={document.source_hash} />
      <Fact label="PDF blob" value={document.pdf_blob_hash ?? "—"} />
      <Fact label="Simhash" value={document.simhash ?? "—"} />
    </div>
  );
}
