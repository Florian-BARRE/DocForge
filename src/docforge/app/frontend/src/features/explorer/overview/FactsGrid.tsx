// ====== Code Summary ======
// The document's own parse-time facts as a compact label/value grid — everything DocumentDetail
// carries besides its metadata list and the fields already shown in the page header. Also exposes
// the blob affordances (download the ORIGINAL file, view the canonical PDF — content-hash routes)
// plus the on-the-fly markdown/HTML VIEWS generated fresh from the IR on every request (NOT stored
// blobs — see api/explorer.ts's documentViewUrl doc). All four go through authenticated fetches.

import { useState } from "react";
import { downloadBlob, openBlobInNewTab } from "../../../api/blobs";
import {
  documentViewFilename,
  downloadDocumentView,
  openDocumentViewInNewTab,
  type DocumentDetail,
  type DocumentViewFormat,
} from "../../../api/explorer";
import { HttpError } from "../../../api/http";
import { Button } from "../../../components/Button";
import { humanizeEnumOption } from "../../../components/schema-form/fieldLabels";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { formatDateTime } from "../format";

const VIEW_LABEL: Record<DocumentViewFormat, string> = { markdown: "markdown", html: "HTML" };

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

/** One format's row: a mono format chip + label/hint, with grouped View and Download actions on the
 *  right. Keeps every format's actions together (no more one flat wrapping row of loose buttons). */
function FormatRow({
  tag,
  label,
  hint,
  busy,
  divider,
  onView,
  onDownload,
}: {
  tag: string;
  label: string;
  hint: string;
  busy: string | null;
  divider?: boolean;
  onView?: () => void;
  onDownload?: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: theme.space.m,
        padding: `${theme.space.s}px ${theme.space.m}px`,
        borderTop: divider ? `1px solid ${theme.color.line}` : undefined,
      }}
    >
      <span
        aria-hidden
        style={{
          flex: "none",
          minWidth: 44,
          textAlign: "center",
          fontFamily: theme.font.mono,
          fontSize: theme.font.size.xs,
          fontWeight: theme.font.weight.semibold,
          color: theme.color.capability,
          background: theme.color.surface2,
          border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.s,
          padding: "2px 6px",
        }}
      >
        {tag}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: theme.font.size.m, color: theme.color.text }}>{label}</div>
        <div style={{ fontSize: theme.font.size.xs, color: theme.color.mute }}>{hint}</div>
      </div>
      <div style={{ display: "flex", gap: theme.space.xs, flex: "none" }}>
        {onView && (
          <Button size="sm" variant="ghost" disabled={busy !== null} onClick={onView}>
            View
          </Button>
        )}
        {onDownload && (
          <Button size="sm" disabled={busy !== null} onClick={onDownload}>
            Download
          </Button>
        )}
      </div>
    </div>
  );
}

export function FactsGrid({ document }: { document: DocumentDetail }) {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  const errorMessage = (error: unknown) => (error instanceof HttpError ? error.message : String(error));

  // One shared runner so every format row's View/Download shares the same busy-lock + error toast.
  const run = async (key: string, action: () => Promise<void>, failLabel: string) => {
    setBusy(key);
    try {
      await action();
    } catch (error) {
      toast.error(`${failLabel} — ${errorMessage(error)}`);
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

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        <div style={{ fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.text }}>
          Download &amp; view
        </div>
        <div style={{ border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, overflow: "hidden" }}>
          <FormatRow
            tag="RAW"
            label="Original file"
            hint={`The uploaded ${document.format.toUpperCase()}, byte-for-byte`}
            busy={busy}
            onView={() => run("original-view", () => openBlobInNewTab(document.source_hash), "Could not open the file")}
            onDownload={() => run("original-download", () => downloadBlob(document.source_hash, document.filename), "Download failed")}
          />
          {document.pdf_blob_hash && (
            <FormatRow
              tag="PDF"
              label="PDF"
              hint="Canonical render used for page previews"
              busy={busy}
              divider
              onView={() => run("pdf-view", () => openBlobInNewTab(document.pdf_blob_hash as string), "Could not open the PDF")}
              onDownload={() =>
                run("pdf-download", () => downloadBlob(document.pdf_blob_hash as string, documentViewFilename(document.filename, "html").replace(/\.html$/, ".pdf")), "Download failed")
              }
            />
          )}
          {(["markdown", "html"] as DocumentViewFormat[]).map((format) => (
            <FormatRow
              key={format}
              tag={format === "markdown" ? "MD" : "HTML"}
              label={VIEW_LABEL[format] === "HTML" ? "HTML" : "Markdown"}
              hint="Generated on the fly from the canonical IR"
              busy={busy}
              divider
              onView={() => run(`${format}-view`, () => openDocumentViewInNewTab(document.id, format), `Could not open the ${VIEW_LABEL[format]} view`)}
              onDownload={() =>
                run(`${format}-download`, () => downloadDocumentView(document.id, format, documentViewFilename(document.filename, format)), "Download failed")
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}
