// ====== Code Summary ======
// The collections-list import panel — mirrors UploadPanel's inline-card placement under the page
// header. Picks a .dcexport bundle (+ optional target name), streams it via FormData (the browser
// handles the multipart streaming), then hands the live state to ImportProgress.

import { useState } from "react";
import { importCollection } from "../../../api/transfers";
import { Button } from "../../../components/Button";
import { FormField } from "../../../components/FormField";
import { inputStyle } from "../../../components/inputStyle";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import { ImportProgress } from "./ImportProgress";

interface ImportPanelProps {
  onNavigate: Navigate;
}

export function ImportPanel({ onNavigate }: ImportPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [targetName, setTargetName] = useState("");
  const [transferId, setTransferId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const start = async () => {
    if (!file) return;
    setUploading(true);
    setStartError(null);
    try {
      const accepted = await importCollection(file, targetName.trim() || undefined);
      setTransferId(accepted.transfer_id);
    } catch (e) {
      setStartError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
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
      <div style={{ fontSize: theme.font.size.l, fontWeight: 700, color: theme.color.text }}>Import collection</div>

      {!transferId && (
        <>
          <FormField label="Bundle" hint="A .dcexport file produced by another DocForge server's export.">
            <input
              type="file"
              accept=".dcexport"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ fontSize: theme.font.size.s, color: theme.color.text }}
            />
          </FormField>
          <FormField label="Name (optional)" hint="Defaults to the bundle's original collection name.">
            <input
              type="text"
              value={targetName}
              onChange={(e) => setTargetName(e.target.value)}
              placeholder="new-collection-name"
              style={inputStyle}
            />
          </FormField>
          {startError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{startError}</div>}
          <div>
            <Button variant="secondary" disabled={!file || uploading} onClick={start}>
              {uploading ? "uploading…" : "Start import"}
            </Button>
          </div>
        </>
      )}

      {transferId && <ImportProgress transferId={transferId} onNavigate={onNavigate} />}
    </div>
  );
}
