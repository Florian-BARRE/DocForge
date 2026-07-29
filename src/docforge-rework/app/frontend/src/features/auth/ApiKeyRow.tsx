// ====== Code Summary ======
// One stored key's summary row — name, prefix, scoped permissions, expiry + last-used status, and
// revoke/rotate actions. Revoke keeps its inline-confirm (mirroring CollectionDetailPage's delete
// confirmation); rotate just hands off to the parent, which reuses CreateKeyForm in "rotate" mode.

import { useState } from "react";
import { revokeKey, type ApiKeyInfo } from "../../api/auth";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";
import { ExpiryChip } from "./ExpiryChip";
import { describeScope } from "./permissionsSummary";
import { humanizeAgo } from "./relativeTime";

interface ApiKeyRowProps {
  apiKey: ApiKeyInfo;
  onRevoked: () => void;
  onRotate: () => void;
  /** Best-effort collection id→name map, used to spell out scoped grants by name. */
  collectionNames: Map<string, string>;
}

function formatTimestamp(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export function ApiKeyRow({ apiKey, onRevoked, onRotate, collectionNames }: ApiKeyRowProps) {
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
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.m,
        display: "flex", flexDirection: "column", gap: theme.space.xs,
        opacity: revoked ? 0.6 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
        <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text }}>
          {apiKey.name}
        </strong>
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.s, color: theme.color.dim }}>
          {apiKey.prefix}…
        </span>
        <Chip tone={revoked ? "dim" : "ok"}>{revoked ? "revoked" : "active"}</Chip>
        <ExpiryChip expiresAt={apiKey.expires_at} />
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
            <>
              <Button variant="secondary" onClick={onRotate}>Rotate</Button>
              <Button variant="danger" onClick={() => setConfirming(true)}>Revoke</Button>
            </>
          )}
        </div>
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        {describeScope(apiKey.permissions, collectionNames)}
      </div>
      <div style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>
        created: {formatTimestamp(apiKey.created_at)}
        {revoked && <> · revoked: {formatTimestamp(apiKey.revoked_at)}</>}
        {" · "}
        {apiKey.last_used_at ? `last used ${humanizeAgo(apiKey.last_used_at)}` : "never used"}
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</div>}
    </div>
  );
}
