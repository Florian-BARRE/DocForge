// ====== Code Summary ======
// The corpus toolbar's mass re-ingestion actions — re-run the FULL pipeline on every document in
// the collection, or just the selected subset. Both paths share one two-step inline confirm (same
// shape as DocumentRow's delete confirm) since a re-ingest re-spends the whole pipeline per doc.

import { useState } from "react";
import { reingestCollection } from "../../api/collections";
import { HttpError } from "../../api/http";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";

type ReingestTarget = "all" | "selected";

interface ReingestToolbarProps {
  collectionId: string;
  totalCount: number;
  selectedIds: string[];
  /** Fired after a successful queue — the caller clears selection / refetches the list. */
  onQueued: () => void;
}

export function ReingestToolbar({ collectionId, totalCount, selectedIds, onQueued }: ReingestToolbarProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState<ReingestTarget | null>(null);
  const [pending, setPending] = useState(false);

  const selectedCount = selectedIds.length;
  const confirmCount = confirming === "all" ? totalCount : selectedCount;

  const run = async () => {
    if (!confirming) return;
    setPending(true);
    try {
      const response = await reingestCollection(collectionId, confirming === "selected" ? selectedIds : undefined);
      const noun = response.count === 1 ? "document" : "documents";
      toast.success(`${response.count} ${noun} queued for re-ingestion — see the Jobs tab`);
      setConfirming(null);
      onQueued();
    } catch (e) {
      toast.error(e instanceof HttpError ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  if (confirming) {
    return (
      <span style={{ display: "inline-flex", gap: theme.space.s, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          Re-run the full pipeline on {confirming === "all" ? "all " : ""}
          {confirmCount} document{confirmCount === 1 ? "" : "s"}?
        </span>
        <Button variant="primary" size="sm" disabled={pending} onClick={run}>
          {pending ? "queuing…" : "Confirm re-ingest"}
        </Button>
        <Button size="sm" disabled={pending} onClick={() => setConfirming(null)}>Cancel</Button>
      </span>
    );
  }

  return (
    <span style={{ display: "inline-flex", gap: theme.space.s, alignItems: "center" }}>
      <Button size="sm" disabled={totalCount === 0} onClick={() => setConfirming("all")}>Re-ingest all</Button>
      {selectedCount > 0 && (
        <Button size="sm" onClick={() => setConfirming("selected")}>Re-ingest selected ({selectedCount})</Button>
      )}
    </span>
  );
}
