// ====== Code Summary ======
// The document's blob affordances (download the ORIGINAL file, view the canonical PDF —
// content-hash routes) plus the on-the-fly markdown/HTML VIEWS generated fresh from the IR on every
// request (NOT stored blobs — see api/explorer.ts's documentViewUrl doc). All four go through
// authenticated fetches. The parse-time facts these used to sit alongside now live in
// SystemMetadataPanel.

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
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";

const VIEW_LABEL: Record<DocumentViewFormat, string> = { markdown: "markdown", html: "HTML" };

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

export function DownloadsPanel({ document }: { document: DocumentDetail }) {
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
    <div style={{ border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, overflow: "hidden" }}>
      <FormatRow
        tag="RAW"
        label="Original file"
        hint={`The uploaded ${document.format.toUpperCase()}, byte-for-byte`}
        busy={busy}
        onView={() => run("original-view", () => openBlobInNewTab(document.source_hash, document.filename), "Could not open the file")}
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
          hint="Generated on the fly from the document's parsed content, not a stored file"
          busy={busy}
          divider
          onView={() => run(`${format}-view`, () => openDocumentViewInNewTab(document.id, format), `Could not open the ${VIEW_LABEL[format]} view`)}
          onDownload={() =>
            run(`${format}-download`, () => downloadDocumentView(document.id, format, documentViewFilename(document.filename, format)), "Download failed")
          }
        />
      ))}
    </div>
  );
}
