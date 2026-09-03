// ====== Code Summary ======
// The collection's one destructive action — deletion — as its own clearly-marked block on the edit
// wizard (the closest thing this app has to a "Settings" screen for an existing collection). Kept
// out of the Metadata tab it used to live under so it reads as a deliberate settings action, not a
// side-effect of editing the schema table. This is one of THREE delete entry points now — the other
// two (dashboard card overflow menu, collection detail header overflow menu) are more discoverable
// but share this component's underlying request/toast path via `state/useDeleteCollection`; this
// one keeps its own inline (non-modal) confirm since it already lives on a dedicated settings screen.

import { useState } from "react";
import { Button } from "../../../components/Button";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import { useDeleteCollection } from "../state/useDeleteCollection";

interface DangerZoneProps {
  collectionId: string;
  collectionName: string;
  onNavigate: Navigate;
}

export function DangerZone({ collectionId, collectionName, onNavigate }: DangerZoneProps) {
  const [confirming, setConfirming] = useState(false);
  const { deleting, error, remove } = useDeleteCollection();

  const handleDelete = async () => {
    const ok = await remove({ id: collectionId, name: collectionName });
    if (ok) onNavigate({ name: "collections" });
  };

  return (
    <div
      style={{
        marginTop: theme.space.xl, padding: theme.space.l,
        border: `1px solid ${theme.color.error}`, borderRadius: theme.radius.l,
        background: theme.color.errorSoft,
        display: "flex", flexDirection: "column", gap: theme.space.m,
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
          Deleting <strong>{collectionName}</strong> removes it and every document indexed under it.
          This cannot be undone.
        </div>
        <div style={{ display: "flex", gap: theme.space.s, flexShrink: 0 }}>
          {confirming ? (
            <>
              <Button onClick={() => setConfirming(false)} disabled={deleting}>Cancel</Button>
              <Button variant="danger" disabled={deleting} onClick={handleDelete}>
                {deleting ? "deleting…" : "Confirm delete"}
              </Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirming(true)}>Delete collection</Button>
          )}
        </div>
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
    </div>
  );
}
