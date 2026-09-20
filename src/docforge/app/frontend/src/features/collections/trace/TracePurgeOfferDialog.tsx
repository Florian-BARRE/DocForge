// ====== Code Summary ======
// The offer-on-disable modal: shown right after a collection's `trace_verbosity` is saved DOWN from
// 'full', asking whether to also reclaim the heavy trace payloads already stored under the old
// setting. Never blocks the verbosity change itself — the PATCH has already succeeded by the time
// this renders; declining just moves on. Portaled to `document.body` — several page wrappers in this
// app carry the `df-rise` entrance CSS animation, which silently confines an in-tree
// `position: fixed` overlay to that ancestor's box in Chromium (see PageBoxLightbox.tsx).

import { useId } from "react";
import { createPortal } from "react-dom";
import { Button } from "../../../components/Button";
import { useFocusTrap } from "../../../shell/useFocusTrap";
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
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onDone);
  const { traceBytes, loading: traceBytesLoading } = useCollectionTraceBytes(collectionId);
  const { pending, error, purge } = useCollectionTracePurge(collectionId);

  const handleConfirm = async () => {
    await purge();
    onDone();
  };

  return createPortal(
    <div
      onClick={onDone}
      style={{
        position: "fixed", inset: 0, background: theme.color.overlay, backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: theme.color.panel, border: `1px solid ${theme.color.accentLine}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 440, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          Delete the stored heavy traces?
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
          Execution trace verbosity was lowered from Full. Full raw payloads already recorded while it
          was Full remain in object storage until purged — new runs will only keep the lightweight
          summary from now on.
        </div>
        <div style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xl, color: theme.color.accentSafe, fontWeight: 700 }}>
          {traceBytesLoading ? "…" : formatBytes(traceBytes ?? 0)} stored
        </div>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onDone}>Not now</Button>
          <Button variant="danger" size="sm" disabled={pending} onClick={handleConfirm}>
            {pending ? "deleting…" : "Yes, delete them"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
