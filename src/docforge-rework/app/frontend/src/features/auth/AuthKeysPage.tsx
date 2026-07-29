// ====== Code Summary ======
// The "API Keys" page: list of stored keys, an active/revoked/all filter, and the create + rotate
// flows (both driven by the same CreateKeyForm). A page remount refetches (see App.tsx's routing
// convention), so navigating away/back after a mutation always shows fresh data — this page also
// refetches explicitly after each mutation since it stays mounted while they happen.

import { useEffect, useState } from "react";
import { ALL_COLLECTIONS_SCOPE, listKeys, rotateKey, type ApiKeyInfo, type CreatedApiKey } from "../../api/auth";
import { listCollections } from "../../api/collections";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { TabNav } from "../../components/TabNav";
import { theme } from "../../theme";
import { ApiKeyRow } from "./ApiKeyRow";
import { CreatedKeyModal } from "./CreatedKeyModal";
import { CreateKeyForm, type CreateKeyFormInitial } from "./CreateKeyForm";
import { isoToExpiryChoice } from "./expiry";

type StatusFilter = "active" | "revoked" | "all";

/**
 * Pre-fill the rotate form from the key it is replacing — same name/permissions/expiry, editable
 * before submit (the backend clones omitted fields, but the UI always sends a full override).
 *
 * @param key - The key selected for rotation.
 * @returns The `CreateKeyForm` initial state for "rotate" mode.
 */
function deriveRotateInitial(key: ApiKeyInfo): CreateKeyFormInitial {
  const permissions = key.permissions;
  return {
    name: key.name,
    fullAccess: permissions === null,
    capabilities: permissions?.capabilities ?? ["read"],
    collectionsScope: !permissions || permissions.collections.includes(ALL_COLLECTIONS_SCOPE) ? "all" : permissions.collections,
    expiry: isoToExpiryChoice(key.expires_at),
  };
}

export function AuthKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [rotatingKey, setRotatingKey] = useState<ApiKeyInfo | null>(null);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);
  const [collectionNames, setCollectionNames] = useState<Map<string, string>>(new Map());
  const [filter, setFilter] = useState<StatusFilter>("active");

  const load = () => {
    setError(null);
    listKeys()
      .then(setKeys)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, []);
  useEffect(() => {
    // Best-effort — a failed fetch just falls back to id slices in the row summaries below.
    listCollections()
      .then((collections) => setCollectionNames(new Map(collections.map((c) => [c.id, c.name]))))
      .catch(() => {});
  }, []);

  const handleCreated = (created: CreatedApiKey) => {
    setShowCreate(false);
    setRotatingKey(null);
    setCreatedKey(created);
    load();
  };

  const activeCount = keys?.filter((k) => !k.revoked_at).length ?? 0;
  const revokedCount = keys?.filter((k) => k.revoked_at).length ?? 0;
  const totalCount = keys?.length ?? 0;
  const visibleKeys = keys?.filter((k) => {
    if (filter === "active") return !k.revoked_at;
    if (filter === "revoked") return Boolean(k.revoked_at);
    return true;
  });

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      <PageHeader
        title="API Keys"
        subtitle={keys ? `${totalCount} key${totalCount === 1 ? "" : "s"} — bearer authentication for the API` : " "}
        actions={!showCreate && !rotatingKey && <Button variant="primary" onClick={() => setShowCreate(true)}>+ New key</Button>}
      />

      {keys && keys.length > 0 && (
        <div style={{ marginBottom: theme.space.l }}>
          <TabNav
            tabs={[
              { key: "active", label: `Active (${activeCount})` },
              { key: "revoked", label: `Revoked (${revokedCount})` },
              { key: "all", label: `All (${totalCount})` },
            ]}
            active={filter}
            onSelect={setFilter}
          />
        </div>
      )}

      {showCreate && (
        <div style={{ marginBottom: theme.space.l }}>
          <CreateKeyForm onCreated={handleCreated} onCancel={() => setShowCreate(false)} />
        </div>
      )}
      {rotatingKey && (
        <div style={{ marginBottom: theme.space.l }}>
          <CreateKeyForm
            mode="rotate"
            initial={deriveRotateInitial(rotatingKey)}
            onSubmitOverride={(payload) => rotateKey(rotatingKey.id, payload)}
            onCreated={handleCreated}
            onCancel={() => setRotatingKey(null)}
          />
        </div>
      )}

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !keys && <LoadingState label="loading keys…" />}
      {keys && keys.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
          }}
        >
          No API keys yet — create the first one.
        </div>
      )}
      {keys && keys.length > 0 && visibleKeys?.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
          }}
        >
          No keys match this filter.
        </div>
      )}
      {visibleKeys && visibleKeys.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          {visibleKeys.map((key) => (
            <ApiKeyRow
              key={key.id}
              apiKey={key}
              onRevoked={load}
              onRotate={() => setRotatingKey(key)}
              collectionNames={collectionNames}
            />
          ))}
        </div>
      )}

      {createdKey && <CreatedKeyModal createdKey={createdKey} onClose={() => setCreatedKey(null)} />}
    </div>
  );
}
