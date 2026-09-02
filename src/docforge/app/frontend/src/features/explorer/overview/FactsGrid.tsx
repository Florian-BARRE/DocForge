// ====== Code Summary ======
// The document's own parse-time facts as a compact label/value grid — everything DocumentDetail
// carries besides its metadata list and the fields already shown in the page header. Also exposes
// the blob affordances: download the ORIGINAL file (source_hash) and view the canonical PDF
// (pdf_blob_hash, now populated for HTML/MD too). Both go through the authenticated blobs route.

import { useState } from "react";
import { downloadBlob, openBlobInNewTab } from "../../../api/blobs";
import type { DocumentDetail } from "../../../api/explorer";
import { HttpError } from "../../../api/http";
import { Button } from "../../../components/Button";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { formatDateTime } from "../format";

/** Shortens a long machine value (a hash) to "lead…trail" — the full value stays available via the
 *  `title` tooltip. A no-op below the threshold, so short mono values (mime types, versions) render
 *  untouched. */
function truncateHash(value: string, edge = 10): string {
  return value.length <= edge * 2 + 1 ? value : `${value.slice(0, edge)}…${value.slice(-edge)}`;
}

function Fact({ label, value, mono, hint }: { label: string; value: string; mono?: boolean; hint?: string }) {
  const displayValue = mono ? truncateHash(value) : value;
  return (
    <div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 2 }}>
        {label}
      </div>
      <div
        title={mono && displayValue !== value ? value : undefined}
        style={{ fontSize: theme.font.size.s, color: theme.color.text, wordBreak: "break-all", fontFamily: mono ? theme.font.mono : undefined }}
      >
        {displayValue}
      </div>
      {hint && <div style={{ color: theme.color.mute, fontSize: theme.font.size.xs, marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

export function FactsGrid({ document }: { document: DocumentDetail }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"original" | "pdf" | null>(null);

  const errorMessage = (error: unknown) => (error instanceof HttpError ? error.message : String(error));

  const handleDownloadOriginal = async () => {
    setBusy("original");
    try {
      await downloadBlob(document.source_hash, document.filename);
    } catch (error) {
      toast.error(`Download failed — ${errorMessage(error)}`);
    } finally {
      setBusy(null);
    }
  };

  const handleViewPdf = async () => {
    if (!document.pdf_blob_hash) return;
    setBusy("pdf");
    try {
      await openBlobInNewTab(document.pdf_blob_hash);
    } catch (error) {
      toast.error(`Could not open PDF — ${errorMessage(error)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: theme.space.l }}>
        <Fact label="Format" value={document.format} />
        <Fact label="MIME type" value={document.mime_type} mono />
        <Fact label="Source kind" value={humanizeEnumOption(document.source_kind)} />
        <Fact label="Title" value={document.title || "—"} />
        <Fact label="Language" value={document.language || "—"} />
        <Fact label="Pipeline version" value={document.pipeline_version} mono />
        <Fact label="Admitted" value={formatDateTime(document.created_at)} />
        <Fact label="Source hash" value={document.source_hash} mono hint="sha256 of the original uploaded file" />
        <Fact
          label="PDF blob"
          value={document.pdf_blob_hash ?? "—"}
          mono
          hint="sha256 of the canonical PDF render used for page previews (distinct from the source hash for non-PDF uploads)"
        />
        <Fact label="Simhash" value={document.simhash ?? "—"} mono hint="near-duplicate fingerprint" />
      </div>

      <div style={{ display: "flex", gap: theme.space.s, flexWrap: "wrap" }}>
        <Button size="sm" disabled={busy !== null} onClick={handleDownloadOriginal}>
          {busy === "original" ? "preparing…" : "Download original"}
        </Button>
        {document.pdf_blob_hash && (
          <Button size="sm" disabled={busy !== null} onClick={handleViewPdf}>
            {busy === "pdf" ? "opening…" : "View PDF"}
          </Button>
        )}
      </div>
    </div>
  );
}
