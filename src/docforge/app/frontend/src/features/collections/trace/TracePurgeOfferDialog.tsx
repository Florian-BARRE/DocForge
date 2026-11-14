// ====== Code Summary ======
// The offer-on-disable modal: shown right after a collection's `trace_verbosity` is saved DOWN from
// 'full', asking whether to also reclaim the heavy trace payloads already stored under the old
// setting. Never blocks the verbosity change itself — the PATCH has already succeeded by the time
// this renders; declining just moves on. The overlay shell is the shared `ConfirmDialog` (declining,
// Escape and the backdrop all resolve through `onDone`).

import { ConfirmDialog } from "../../../components/dialog/ConfirmDialog";
import { theme } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { useCollectionTraceBytes } from "./useCollectionTraceBytes";
import { useCollectionTracePurge } from "./useCollectionTracePurge";

interface TracePurgeOfferDialogProps {
  collectionId: string;
  /** Called once the choice is resolved — after a successful/failed purge attempt, or on decline. */
  onDone: () => void;
}

export function TracePurgeOfferDialog({ collectionId, onDone }: TracePurgeOfferDialogProps) {
  const { traceBytes, loading: traceBytesLoading } = useCollectionTraceBytes(collectionId);
  const { pending, error, purge } = useCollectionTracePurge(collectionId);

  const handleConfirm = async () => {
    await purge();
    onDone();
  };

  return (
    <ConfirmDialog
      title="Delete the stored heavy traces?"
      tone="accent"
      maxWidth={440}
      cancelLabel="Not now"
      confirmVariant="danger"
      confirmLabel="Yes, delete them"
      pendingLabel="deleting…"
      pending={pending}
      error={error}
      onConfirm={handleConfirm}
      onCancel={onDone}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
        Execution trace verbosity was lowered from Full. Full raw payloads already recorded while it
        was Full remain in object storage until purged — new runs will only keep the lightweight
        summary from now on.
      </div>
      <div style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xl, color: theme.color.accentSafe, fontWeight: 700 }}>
        {traceBytesLoading ? "…" : formatBytes(traceBytes ?? 0)} stored
      </div>
    </ConfirmDialog>
  );
}
