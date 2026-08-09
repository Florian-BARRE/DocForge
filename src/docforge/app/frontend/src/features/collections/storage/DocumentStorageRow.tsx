// ====== Code Summary ======
// One document's row in the per-document storage table — click navigates to the document page,
// same affordance as the explorer's own document table. The filename truncates with an ellipsis
// and keeps the full name as a tooltip so a long filename never pushes the byte columns off-screen.

import type { DocumentStorageBreakdown } from "../../../api/collections";
import type { Navigate } from "../../../shell/view";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";

interface DocumentStorageRowProps {
  document: DocumentStorageBreakdown;
  collectionId: string;
  onNavigate: Navigate;
}

const cellStyle: React.CSSProperties = { padding: `${t.space.s}px ${t.space.m}px`, fontSize: t.font.size.s };
const byteCellStyle: React.CSSProperties = { ...cellStyle, textAlign: "right", fontFamily: t.font.mono, color: t.color.dim };

export function DocumentStorageRow({ document, collectionId, onNavigate }: DocumentStorageRowProps) {
  return (
    <tr
      onClick={() => onNavigate({ name: "document", collectionId, documentId: document.document_id })}
      style={{ cursor: "pointer", borderBottom: `1px solid ${t.color.line}`, transition: "background .12s ease" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = t.color.surface2)}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <td style={{ ...cellStyle, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={document.filename}>
        <span style={{ fontWeight: t.font.weight.medium, color: t.color.text }}>{document.filename}</span>
      </td>
      <td style={byteCellStyle}>{formatBytes(document.s3.total_bytes)}</td>
      <td style={byteCellStyle}>{formatBytes(document.postgres.total_bytes)}</td>
      <td style={byteCellStyle}>{formatBytes(document.qdrant.total_bytes)}</td>
      <td style={{ ...byteCellStyle, color: t.color.text, fontWeight: t.font.weight.semibold }}>{formatBytes(document.total_bytes)}</td>
    </tr>
  );
}
