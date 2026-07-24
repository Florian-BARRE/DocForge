// ====== Code Summary ======
// One stored key's summary row — name, prefix, permissions, created date, active/revoked status,
// and a revoke action (inline confirm, mirroring CollectionDetailPage's delete confirmation).

import { useState } from "react";
import { revokeKey, type ApiKeyInfo } from "../../api/auth";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";
import { summarizePermissions } from "./permissionsSummary";

interface ApiKeyRowProps {
  apiKey: ApiKeyInfo;
  onRevoked: () => void;
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function ApiKeyRow({ apiKey, onRevoked }: ApiKeyRowProps) {
  const [confirming, setConfirming] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const revoked = Boolean(apiKey.revoked_at);

  const handleRevoke = async () => {
    setRevoking(true);
    setError(null);
    try {
      await revokeKey(apiKey.id);
      onRevoked();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRevoking(false);
    }
  };

  return (
    <div
      style={{
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: theme.space.m,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong style={{ fontSize: theme.font.size.l }}>{apiKey.name}</strong>
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.dim }}>
          {apiKey.prefix}…
        </span>
        <Chip tone={revoked ? "dim" : "ok"}>{revoked ? "revoked" : "active"}</Chip>
        <div style={{ marginLeft: "auto", display: "flex", gap: theme.space.s }}>
          {revoked ? null : confirming ? (
            <>
              <span style={{ color: theme.color.dim, fontSize: theme.font.size.s, alignSelf: "center" }}>Revoke for good?</span>
              <Button variant="danger" disabled={revoking} onClick={handleRevoke}>
                {revoking ? "revoking…" : "Confirm revoke"}
              </Button>
              <Button onClick={() => setConfirming(false)}>Cancel</Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirming(true)}>Revoke</Button>
          )}
        </div>
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{summarizePermissions(apiKey.permissions)}</div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
        created: {formatTimestamp(apiKey.created_at)}
        {revoked && <> · revoked: {formatTimestamp(apiKey.revoked_at)}</>}
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</div>}
    </div>
  );
}
