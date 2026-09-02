// ====== Code Summary ======
// The collection's one destructive action — deletion — as its own clearly-marked block on the edit
// wizard (the closest thing this app has to a "Settings" screen for an existing collection). Kept
// out of the Metadata tab it used to live under so it reads as a deliberate settings action, not a
// side-effect of editing the schema table.

import { useState } from "react";
import { deleteCollection } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { useToast } from "../../../shell/toast";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";

interface DangerZoneProps {
  collectionId: string;
  collectionName: string;
  onNavigate: Navigate;
}

export function DangerZone({ collectionId, collectionName, onNavigate }: DangerZoneProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteCollection(collectionId);
      toast.success(`Collection “${collectionName}” deleted`);
      onNavigate({ name: "collections" });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error(`Delete failed — ${message}`);
      setDeleting(false);
    }
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
