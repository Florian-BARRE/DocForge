// ====== Code Summary ======
// The collection export panel — mirrors UploadPanel's inline-card placement under the collection
// header (CollectionShell owns the show/hide toggle). Opens the export transfer on demand, then
// hands the live state to ExportProgress for polling + the eventual authenticated download.

import { useState } from "react";
import { exportCollection } from "../../../api/transfers";
import { Button } from "../../../components/Button";
import { theme } from "../../../theme";
import { ExportProgress } from "./ExportProgress";

interface ExportPanelProps {
  collectionId: string;
  collectionName: string;
}

export function ExportPanel({ collectionId, collectionName }: ExportPanelProps) {
  const [transferId, setTransferId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const start = async () => {
    setStarting(true);
    setStartError(null);
    try {
      const accepted = await exportCollection(collectionId);
      setTransferId(accepted.transfer_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m, width: "100%", maxWidth: 460,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
      }}
    >
      <div>
        <div style={{ fontSize: theme.font.size.l, fontWeight: 700, color: theme.color.text }}>Export collection</div>
        <div style={{ fontSize: theme.font.size.s, color: theme.color.dim, marginTop: 4 }}>
          Bundles the schema, documents, IR and vectors into a portable{" "}
          <span style={{ fontFamily: theme.font.mono }}>.dcexport</span> file you can import on another
          DocForge server.
        </div>
      </div>

      {!transferId && (
        <div>
          <Button variant="secondary" disabled={starting} onClick={start}>{starting ? "starting…" : "Start export"}</Button>
        </div>
      )}
      {startError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{startError}</div>}

      {transferId && <ExportProgress transferId={transferId} collectionName={collectionName} />}
    </div>
  );
}
