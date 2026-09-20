// ====== Code Summary ======
// The collection's two heaviest-consequence actions, both requiring an explicit confirm: deleting
// the collection outright, and re-running the full ingestion pipeline over every document in it
// (purges existing chunks/IR/pages, re-embeds — same full-pipeline re-run as a single document's
// row action, just collection-wide). Kept clearly separated by a divider so a misclick can't
// conflate "expensive but recoverable" (reingest) with "irreversible" (delete). This is one of
// THREE delete entry points now — the other two (dashboard card overflow menu, collection detail
// header overflow menu) are more discoverable but share this component's underlying request/toast
// path via `state/useDeleteCollection`; this one keeps its own inline (non-modal) confirm since it
// already lives on a dedicated settings screen.

import { useState } from "react";
import { reingestCollection } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { useToast } from "../../../shell/toast";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { useDeleteCollection } from "../state/useDeleteCollection";
import { useCollectionTraceBytes } from "../trace/useCollectionTraceBytes";
import { useCollectionTracePurge } from "../trace/useCollectionTracePurge";

interface DangerZoneProps {
  collectionId: string;
  collectionName: string;
  onNavigate: Navigate;
}

export function DangerZone({ collectionId, collectionName, onNavigate }: DangerZoneProps) {
  const toast = useToast();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const { deleting, error: deleteError, remove } = useDeleteCollection();
  const [confirmingReingest, setConfirmingReingest] = useState(false);
  const [reingesting, setReingesting] = useState(false);
  const [reingestError, setReingestError] = useState<string | null>(null);
  const { traceBytes, loading: traceBytesLoading } = useCollectionTraceBytes(collectionId);
  const { pending: purgingTraces, error: purgeTracesError, purge: purgeTraces } = useCollectionTracePurge(collectionId);
  const [confirmingTracePurge, setConfirmingTracePurge] = useState(false);

  const handleDelete = async () => {
    const ok = await remove({ id: collectionId, name: collectionName });
    if (ok) onNavigate({ name: "collections" });
  };

  const handlePurgeTraces = async () => {
    const result = await purgeTraces();
    if (result) setConfirmingTracePurge(false);
  };

  const handleReingest = async () => {
    setReingesting(true);
    setReingestError(null);
    try {
      const result = await reingestCollection(collectionId);
      setConfirmingReingest(false);
      toast.success(`Full reingest queued for ${result.count} document${result.count === 1 ? "" : "s"}.`);
      onNavigate({ name: "collection-activity", collectionId });
    } catch (e) {
      setReingestError(e instanceof Error ? e.message : String(e));
    } finally {
      setReingesting(false);
    }
  };

  return (
    <div
      style={{
        padding: theme.space.l,
        border: `1px solid ${theme.color.error}`, borderRadius: theme.radius.l,
        background: theme.color.errorSoft,
        display: "flex", flexDirection: "column", gap: theme.space.l,
      }}
    >
      <div style={{ fontSize: theme.font.size.l, fontWeight: theme.font.weight.bold, color: theme.color.error }}>
        Danger zone
      </div>

      <div
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m,
          flexWrap: "wrap",
        }}
      >
        <div style={{ color: theme.color.text, fontSize: theme.font.size.s, maxWidth: 480 }}>
          <strong>Full reingest</strong> re-runs the whole pipeline over every document in{" "}
          <strong>{collectionName}</strong> — existing chunks, IR and vectors are purged and rebuilt.
        </div>
        <div style={{ display: "flex", gap: theme.space.s, flexShrink: 0 }}>
          {confirmingReingest ? (
            <>
              <Button onClick={() => setConfirmingReingest(false)} disabled={reingesting}>Cancel</Button>
              <Button variant="danger" disabled={reingesting} onClick={handleReingest}>
                {reingesting ? "queuing…" : "Confirm reingest"}
              </Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirmingReingest(true)}>Full reingest</Button>
          )}
        </div>
      </div>
      {reingestError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{reingestError}</div>}

      <div style={{ borderTop: `1px solid ${theme.color.error}`, opacity: 0.4 }} />

      <div
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m,
          flexWrap: "wrap",
        }}
      >
        <div style={{ color: theme.color.text, fontSize: theme.font.size.s, maxWidth: 480 }}>
          <strong>Purge stored traces</strong> reclaims the heavy full execution-trace payloads
          accumulated while verbosity was set to Full
          {!traceBytesLoading && traceBytes !== null && (
            <>
              {" — currently "}
              <span style={{ fontFamily: theme.font.mono, color: theme.color.text }}>{formatBytes(traceBytes)}</span>
              {" stored."}
            </>
          )}
        </div>
        <div style={{ display: "flex", gap: theme.space.s, flexShrink: 0 }}>
          {confirmingTracePurge ? (
            <>
              <Button onClick={() => setConfirmingTracePurge(false)} disabled={purgingTraces}>Cancel</Button>
              <Button variant="danger" disabled={purgingTraces} onClick={handlePurgeTraces}>
                {purgingTraces ? "purging…" : "Confirm purge"}
              </Button>
            </>
          ) : (
            <Button variant="danger" disabled={!traceBytes} onClick={() => setConfirmingTracePurge(true)}>
              Purge stored traces
            </Button>
          )}
        </div>
      </div>
      {purgeTracesError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{purgeTracesError}</div>}

      <div style={{ borderTop: `1px solid ${theme.color.error}`, opacity: 0.4 }} />

      <div
        style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m,
          flexWrap: "wrap",
        }}
      >
        <div style={{ color: theme.color.text, fontSize: theme.font.size.s, maxWidth: 480 }}>
          <strong>Delete collection</strong> removes <strong>{collectionName}</strong> and every
          document indexed under it. This cannot be undone.
        </div>
        <div style={{ display: "flex", gap: theme.space.s, flexShrink: 0 }}>
          {confirmingDelete ? (
            <>
              <Button onClick={() => setConfirmingDelete(false)} disabled={deleting}>Cancel</Button>
              <Button variant="danger" disabled={deleting} onClick={handleDelete}>
                {deleting ? "deleting…" : "Confirm delete"}
              </Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete collection</Button>
          )}
        </div>
      </div>
      {deleteError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{deleteError}</div>}
    </div>
  );
}
