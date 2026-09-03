// ====== Code Summary ======
// The whole-collection export flow — byte-identical to the original ExportPanel body, extracted
// unchanged so ExportPanel can offer it as one of two scopes (the other being a config snippet).
// Opens an async `.dcexport` transfer, then hands the live state to ExportProgress for polling +
// the eventual authenticated download.

import { useState } from "react";
import { exportCollection } from "../../../api/transfers";
import { Button } from "../../../components/Button";
import { theme } from "../../../theme";
import { ExportProgress } from "./ExportProgress";

interface ExportCollectionSectionProps {
  collectionId: string;
  collectionName: string;
}

export function ExportCollectionSection({ collectionId, collectionName }: ExportCollectionSectionProps) {
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
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
        Bundles the schema, documents, IR and vectors into a portable{" "}
        <span style={{ fontFamily: theme.font.mono }}>.dcexport</span> file you can import on another
        DocForge server.
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
