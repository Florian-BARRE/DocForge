// ====== Code Summary ======
// The "API Keys" page: list of stored keys + create flow. A page remount refetches (see App.tsx's
// routing convention), so navigating away/back after a create or revoke always shows fresh data —
// this page also refetches explicitly after each mutation since it stays mounted while they happen.

import { useEffect, useState } from "react";
import { listKeys, type ApiKeyInfo, type CreatedApiKey } from "../../api/auth";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { ApiKeyRow } from "./ApiKeyRow";
import { CreatedKeyModal } from "./CreatedKeyModal";
import { CreateKeyForm } from "./CreateKeyForm";

export function AuthKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);

  const load = () => {
    setError(null);
    listKeys()
      .then(setKeys)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, []);

  const handleCreated = (created: CreatedApiKey) => {
    setShowCreate(false);
    setCreatedKey(created);
    load();
  };

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: theme.space.l }}>
        <h1 style={{ fontSize: theme.font.size.xl }}>API Keys</h1>
        <div style={{ marginLeft: "auto" }}>
          {!showCreate && <Button variant="primary" onClick={() => setShowCreate(true)}>+ New key</Button>}
        </div>
      </div>

      {showCreate && (
        <div style={{ marginBottom: theme.space.l }}>
          <CreateKeyForm onCreated={handleCreated} onCancel={() => setShowCreate(false)} />
        </div>
      )}

      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !keys && <LoadingState label="loading keys…" />}
      {keys && keys.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No API keys yet — create the first one.</div>
      )}
      {keys && keys.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          {keys.map((key) => <ApiKeyRow key={key.id} apiKey={key} onRevoked={load} />)}
        </div>
      )}

      {createdKey && <CreatedKeyModal createdKey={createdKey} onClose={() => setCreatedKey(null)} />}
    </div>
  );
}
