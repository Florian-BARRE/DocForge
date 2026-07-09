// ====== Code Summary ======
// One document row in the collection's document table — click navigates to the document page;
// delete is a two-step inline confirm (same pattern as CollectionDetailPage's collection delete).

import { useState } from "react";
import type { DocumentListItem } from "../../api/explorer";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";
import { DocumentEnabledToggle } from "./DocumentEnabledToggle";
import { DocumentStatusChip } from "./DocumentStatusChip";
import { formatBytes, formatDateTime } from "./format";

interface DocumentRowProps {
  document: DocumentListItem;
  onOpen: () => void;
  onDelete: () => Promise<void>;
  onEnabledChanged: (enabled: boolean) => void;
}

const cellStyle: React.CSSProperties = { padding: theme.space.s, fontSize: theme.font.size.s };

export function DocumentRow({ document, onOpen, onDelete, onEnabledChanged }: DocumentRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async (event: React.MouseEvent) => {
    event.stopPropagation();
    setDeleting(true);
    setError(null);
    try {
      await onDelete();
      // No need to reset local state on success — the row disappears once the parent refetches.
    } catch (e) {
      setDeleting(false);
      setConfirming(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <tr
      onClick={onOpen}
      style={{ cursor: "pointer", borderBottom: `1px solid ${theme.color.line}`, opacity: document.enabled ? 1 : 0.55 }}
      onMouseEnter={(e) => (e.currentTarget.style.background = theme.color.cardHover)}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <td style={cellStyle}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
          {document.filename}
          {!document.enabled && <Chip tone="warn">disabled</Chip>}
        </span>
      </td>
      <td style={cellStyle}><DocumentStatusChip status={document.status} /></td>
      <td style={{ ...cellStyle, textAlign: "right" }}>{document.page_count ?? "—"}</td>
      <td style={{ ...cellStyle, textAlign: "right" }}>{formatBytes(document.file_size)}</td>
      <td style={cellStyle}>{formatDateTime(document.created_at)}</td>
      <td style={cellStyle} onClick={(e) => e.stopPropagation()}>
        <DocumentEnabledToggle documentId={document.id} enabled={document.enabled} onChanged={onEnabledChanged} />
      </td>
      <td style={{ ...cellStyle, textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.xs, marginBottom: 4 }}>{error}</div>}
        {confirming ? (
          <span style={{ display: "inline-flex", gap: theme.space.xs, alignItems: "center" }}>
            <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>delete for good?</span>
            <Button variant="danger" disabled={deleting} onClick={handleDelete}>{deleting ? "…" : "confirm"}</Button>
            <Button onClick={() => setConfirming(false)}>cancel</Button>
          </span>
        ) : (
          <Button variant="danger" onClick={() => setConfirming(true)}>delete</Button>
        )}
      </td>
    </tr>
  );
}
