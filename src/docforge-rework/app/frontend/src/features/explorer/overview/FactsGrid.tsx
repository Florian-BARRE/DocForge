// ====== Code Summary ======
// The document's own parse-time facts as a compact label/value grid — everything DocumentDetail
// carries besides its metadata list and the fields already shown in the page header.

import type { DocumentDetail } from "../../../api/explorer";
import { theme } from "../../../theme";
import { formatDateTime } from "../format";

function Fact({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ fontSize: theme.font.size.s, color: theme.color.text, wordBreak: "break-all", fontFamily: mono ? theme.font.mono : undefined }}>
        {value}
      </div>
    </div>
  );
}

export function FactsGrid({ document }: { document: DocumentDetail }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: theme.space.l }}>
      <Fact label="Format" value={document.format} />
      <Fact label="MIME type" value={document.mime_type} mono />
      <Fact label="Source kind" value={document.source_kind} />
      <Fact label="Title" value={document.title || "—"} />
      <Fact label="Language" value={document.language || "—"} />
      <Fact label="Pipeline version" value={document.pipeline_version} mono />
      <Fact label="Admitted" value={formatDateTime(document.created_at)} />
      <Fact label="Source hash" value={document.source_hash} mono />
      <Fact label="PDF blob" value={document.pdf_blob_hash ?? "—"} mono />
      <Fact label="Simhash" value={document.simhash ?? "—"} mono />
    </div>
  );
}
