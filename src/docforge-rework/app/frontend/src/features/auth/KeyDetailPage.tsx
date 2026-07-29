// ====== Code Summary ======
// A single API key's detail page — the full, uncapped view: every scoped collection by name, all
// capabilities, absolute + relative timestamps, and the rotate/revoke actions. There is no
// GET /auth/keys/{id} endpoint, so the key is derived from listKeys() by id (metadata only, never
// the secret). Rotate reuses CreateKeyForm + the one-time reveal modal; revoke mirrors the row's
// inline confirm.

import { useEffect, useState, type ReactNode } from "react";
import { listKeys, revokeKey, rotateKey, type ApiKeyInfo, type CreatedApiKey } from "../../api/auth";
import { listCollections } from "../../api/collections";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { ALL_COLLECTIONS_SCOPE } from "../../api/auth";
import { CreatedKeyModal } from "./CreatedKeyModal";
import { CreateKeyForm } from "./CreateKeyForm";
import { ExpiryChip } from "./ExpiryChip";
import { deriveRotateInitial } from "./rotateInitial";
import { StaleChip } from "./StaleChip";
import { humanizeAgo, humanizeUntil } from "./relativeTime";

interface KeyDetailPageProps {
  keyId: string;
  onNavigate: Navigate;
}

/** One label/value detail row. */
function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: t.space.m, padding: `${t.space.s}px 0`, borderBottom: `1px solid ${t.color.line}` }}>
      <span style={{ color: t.color.dim, fontSize: t.font.size.m, minWidth: 130, flexShrink: 0 }}>{label}</span>
      <span style={{ color: t.color.text, fontSize: t.font.size.m }}>{value}</span>
    </div>
  );
}

/** Absolute timestamp with a relative suffix, or a fallback for a null instant. */
function whenText(iso: string | null, relative: (v: string) => string, fallback: string): string {
  if (!iso) return fallback;
  return `${new Date(iso).toLocaleString()} · ${relative(iso)}`;
}

/** Spell out a scoped key's collections BY NAME, uncapped (the detail page shows every one). */
function fullScope(collections: string[], collectionNames: Map<string, string>): string {
  if (collections.includes(ALL_COLLECTIONS_SCOPE)) return "all collections";
  if (collections.length === 0) return "no collections";
  return collections.map((id) => collectionNames.get(id) ?? `${id.slice(0, 8)}…`).join(", ");
}

export function KeyDetailPage({ keyId, onNavigate }: KeyDetailPageProps) {
  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null);
  const [collectionNames, setCollectionNames] = useState<Map<string, string>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [rotating, setRotating] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const load = () => {
    setError(null);
    listKeys().then(setKeys).catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, []);
  useEffect(() => {
    // Best-effort — a failed fetch just falls back to id slices in the scope summary.
    listCollections().then((c) => setCollectionNames(new Map(c.map((x) => [x.id, x.name])))).catch(() => {});
  }, []);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!keys) return <LoadingState label="loading key…" />;

  const apiKey = keys.find((k) => k.id === keyId);
  if (!apiKey) {
    return <ErrorState message="Key not found — it may have been deleted." onRetry={() => onNavigate({ name: "api-keys" })} />;
  }

  const revoked = Boolean(apiKey.revoked_at);

  const handleRevoke = async () => {
    setRevoking(true);
    try {
      await revokeKey(apiKey.id);
      onNavigate({ name: "api-keys" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRevoking(false);
    }
  };

  const handleRotated = (created: CreatedApiKey) => {
    setRotating(false);
    setCreatedKey(created);
  };

  return (
    <div className="df-rise" style={{ padding: t.space.xl, maxWidth: 900, margin: "0 auto", overflowY: "auto", height: "100%", width: "100%" }}>
      <PageHeader
        eyebrow={<BackLink label="API Keys" onClick={() => onNavigate({ name: "api-keys" })} />}
        title={
          <span style={{ display: "inline-flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
            {apiKey.name}
            <Chip tone={revoked ? "dim" : "ok"}>{revoked ? "revoked" : "active"}</Chip>
            <ExpiryChip expiresAt={apiKey.expires_at} />
            <StaleChip apiKey={apiKey} />
          </span>
        }
        actions={
          !revoked && !rotating && (
            <>
              <Button variant="secondary" onClick={() => setRotating(true)}>Rotate</Button>
              {confirming ? (
                <>
                  <Button variant="danger" disabled={revoking} onClick={handleRevoke}>{revoking ? "revoking…" : "Confirm revoke"}</Button>
                  <Button onClick={() => setConfirming(false)}>Cancel</Button>
                </>
              ) : (
                <Button variant="danger" onClick={() => setConfirming(true)}>Revoke</Button>
              )}
            </>
          )
        }
      />

      {rotating && (
        <div style={{ marginBottom: t.space.l }}>
          <CreateKeyForm
            mode="rotate"
            initial={deriveRotateInitial(apiKey)}
            onSubmitOverride={(payload) => rotateKey(apiKey.id, payload)}
            onCreated={handleRotated}
            onCancel={() => setRotating(false)}
          />
        </div>
      )}

      <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, padding: t.space.l }}>
        <Field label="Prefix" value={<span style={{ fontFamily: t.font.mono }}>{apiKey.prefix}…</span>} />
        <Field
          label="Capabilities"
          value={
            apiKey.permissions ? (
              <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
                {apiKey.permissions.capabilities.map((c) => <Chip key={c} tone="accent">{c}</Chip>)}
              </span>
            ) : (
              "all (full access)"
            )
          }
        />
        <Field label="Collections" value={apiKey.permissions ? fullScope(apiKey.permissions.collections, collectionNames) : "all collections"} />
        <Field label="Created" value={whenText(apiKey.created_at, humanizeAgo, "—")} />
        <Field label="Expires" value={apiKey.expires_at ? whenText(apiKey.expires_at, humanizeUntil, "—") : "Never"} />
        <Field label="Last used" value={apiKey.last_used_at ? whenText(apiKey.last_used_at, humanizeAgo, "—") : "Never used"} />
        {revoked && <Field label="Revoked" value={whenText(apiKey.revoked_at, humanizeAgo, "—")} />}
      </div>

      {createdKey && (
        <CreatedKeyModal createdKey={createdKey} onClose={() => { setCreatedKey(null); onNavigate({ name: "api-keys" }); }} />
      )}
    </div>
  );
}
