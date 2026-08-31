// ====== Code Summary ======
// The mass-operations bar — appears once a selection exists, offers Re-ingest/Enable/Disable/
// Delete, and always routes through a BulkConfirmDialog naming the affected count first (the
// count is known client-side already — either the ticked-id count or `total - excludeIds.size` —
// no dry-run round-trip needed). Surfaces a capped-reingest note when the fan-out ceiling hit.

import { useState } from "react";
import { bulkDeleteDocuments, bulkReingestDocuments, bulkSetDocumentsEnabled, type DocumentSelector } from "../../api/corpus";
import { HttpError } from "../../api/http";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { BulkConfirmDialog } from "./BulkConfirmDialog";

type BulkAction = "reingest" | "delete" | "disable" | "enable";

interface BulkActionBarProps {
  collectionId: string;
  count: number;
  buildSelector: () => DocumentSelector;
  /** Fired after a successful op — the caller clears the selection and refetches. */
  onDone: () => void;
}

const ACTION_META: Record<BulkAction, { title: string; description: string; confirmLabel: string; variant: "primary" | "danger" }> = {
  reingest: {
    title: "Re-ingest selected documents",
    description: "Re-run the full pipeline on every selected document — this re-spends the whole pipeline per document. Jobs show up on the Jobs tab.",
    confirmLabel: "Re-ingest", variant: "primary",
  },
  delete: {
    title: "Delete selected documents",
    description: "Delete every selected document everywhere — original file, IR, chunks and vectors. This cannot be undone.",
    confirmLabel: "Delete", variant: "danger",
  },
  disable: {
    title: "Disable selected documents",
    description: "Hide every selected document — and all its chunks — from search. Reversible.",
    confirmLabel: "Disable", variant: "primary",
  },
  enable: {
    title: "Enable selected documents",
    description: "Restore every selected document's searchability. Reversible.",
    confirmLabel: "Enable", variant: "primary",
  },
};

export function BulkActionBar({ collectionId, count, buildSelector, onDone }: BulkActionBarProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState<BulkAction | null>(null);
  const [pending, setPending] = useState(false);

  if (count === 0) return null;

  const run = async () => {
    if (!confirming) return;
    setPending(true);
    const selector = buildSelector();
    try {
      if (confirming === "delete") {
        const response = await bulkDeleteDocuments(collectionId, selector);
        toast.success(`Deleted ${response.deleted} of ${response.matched} matching document${response.matched === 1 ? "" : "s"}`);
      } else if (confirming === "disable" || confirming === "enable") {
        const response = await bulkSetDocumentsEnabled(collectionId, confirming === "enable", selector);
        toast.success(`${response.updated} of ${response.matched} document${response.matched === 1 ? "" : "s"} ${confirming === "enable" ? "enabled" : "disabled"}`);
      } else {
        const response = await bulkReingestDocuments(collectionId, selector);
        const remaining = response.matched - response.enqueued;
        const cappedNote = response.capped ? ` — capped at ${response.max_fanout}; run again to continue the remaining ${remaining}` : "";
        toast.success(`Queued ${response.enqueued} of ${response.matched} document${response.matched === 1 ? "" : "s"} for re-ingestion — see the Jobs tab${cappedNote}`);
      }
      setConfirming(null);
      onDone();
    } catch (e) {
      toast.error(e instanceof HttpError ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <div
        style={{
          display: "flex", alignItems: "center", gap: theme.space.s,
          background: theme.color.accentSoft, border: `1px solid ${theme.color.accentLine}`,
          borderRadius: theme.radius.m, padding: `${theme.space.s}px ${theme.space.m}px`,
        }}
      >
        <span style={{ fontSize: theme.font.size.s, color: theme.color.text, fontWeight: 600 }}>
          {count.toLocaleString()} selected
        </span>
        <Button variant="primary" size="sm" onClick={() => setConfirming("reingest")}>Re-ingest</Button>
        <Button size="sm" onClick={() => setConfirming("enable")}>Enable</Button>
        <Button size="sm" onClick={() => setConfirming("disable")}>Disable</Button>
        <Button variant="danger" size="sm" onClick={() => setConfirming("delete")}>Delete</Button>
      </div>
      {confirming && (
        <BulkConfirmDialog
          title={ACTION_META[confirming].title}
          description={ACTION_META[confirming].description}
          count={count}
          confirmLabel={ACTION_META[confirming].confirmLabel}
          variant={ACTION_META[confirming].variant}
          pending={pending}
          onConfirm={run}
          onCancel={() => setConfirming(null)}
        />
      )}
    </>
  );
}
