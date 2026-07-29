// ====== Code Summary ======
// The create/rotate key form — name + permissions builder + expiry picker. In "create" mode it
// calls `createKey` directly; in "rotate" mode (pre-filled from an existing key) the caller
// supplies `onSubmitOverride`, which posts to `/rotate` instead. Either way the plaintext result is
// handed to the parent (AuthKeysPage), which owns the one-time reveal modal and the list refresh —
// this form never keeps a copy of it.

import { useEffect, useState } from "react";
import { createKey, type ApiCapability, type CreatedApiKey, type KeyPermissions } from "../../api/auth";
import { listCollections, type Collection } from "../../api/collections";
import type { ApiIssue } from "../../api/http";
import { HttpError } from "../../api/http";
import { ApiIssueList } from "../../components/ApiIssueList";
import { Button } from "../../components/Button";
import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";
import { expiryToIso, type ExpiryChoice } from "./expiry";
import { ExpirySelector } from "./ExpirySelector";
import { PermissionsBuilder, type CollectionsScope } from "./PermissionsBuilder";

/** Pre-fill values for "rotate" mode — derived from the key being rotated (see AuthKeysPage). */
export interface CreateKeyFormInitial {
  name: string;
  fullAccess: boolean;
  capabilities: ApiCapability[];
  collectionsScope: CollectionsScope;
  expiry: ExpiryChoice;
}

/** The submitted payload — shared shape for both `createKey` and `rotateKey` requests. */
export interface KeyFormPayload {
  name: string;
  permissions: KeyPermissions | null;
  expires_at: string | null;
}

interface CreateKeyFormProps {
  mode?: "create" | "rotate";
  initial?: CreateKeyFormInitial;
  /** Rotate mode supplies this to call `rotateKey(id, payload)` instead of `createKey`. */
  onSubmitOverride?: (payload: KeyFormPayload) => Promise<CreatedApiKey>;
  onCreated: (createdKey: CreatedApiKey) => void;
  onCancel: () => void;
}

export function CreateKeyForm({ mode = "create", initial, onSubmitOverride, onCreated, onCancel }: CreateKeyFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [fullAccess, setFullAccess] = useState(initial?.fullAccess ?? true);
  const [capabilities, setCapabilities] = useState<ApiCapability[]>(initial?.capabilities ?? ["read"]);
  const [collectionsScope, setCollectionsScope] = useState<CollectionsScope>(initial?.collectionsScope ?? "all");
  const [expiry, setExpiry] = useState<ExpiryChoice>(initial?.expiry ?? { kind: "never" });
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [collectionsError, setCollectionsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [issues, setIssues] = useState<ApiIssue[]>([]);

  useEffect(() => {
    listCollections()
      .then(setCollections)
      .catch((error) => {
        setCollections([]);
        setCollectionsError(error instanceof Error ? error.message : String(error));
      });
  }, []);

  const scopedValid = fullAccess || (capabilities.length > 0 && (collectionsScope === "all" || collectionsScope.length > 0));
  const expiryValid = expiry.kind !== "custom" || expiry.date.length > 0;
  const valid = name.trim().length > 0 && scopedValid && expiryValid;
  const isRotate = mode === "rotate";

  const handleSubmit = async () => {
    setSubmitting(true);
    setIssues([]);
    try {
      const payload: KeyFormPayload = {
        name: name.trim(),
        permissions: fullAccess
          ? null
          : { capabilities, collections: collectionsScope === "all" ? ["*"] : collectionsScope },
        expires_at: expiryToIso(expiry),
      };
      const created = onSubmitOverride ? await onSubmitOverride(payload) : await createKey(payload);
      onCreated(created);
    } catch (error) {
      setIssues(error instanceof HttpError ? error.issues : [{ message: String(error) }]);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m,
        background: theme.color.surface, border: `1px solid ${theme.color.accentLine}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
      }}
    >
      <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text, margin: 0 }}>
        {isRotate ? "Rotate key — issues a new secret & revokes the old" : "New API key"}
      </h2>
      <FormField label="Name">
        <input style={inputStyle} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. ingestion-worker-prod" />
      </FormField>
      <PermissionsBuilder
        fullAccess={fullAccess}
        onFullAccessChange={setFullAccess}
        capabilities={capabilities}
        onCapabilitiesChange={setCapabilities}
        collectionsScope={collectionsScope}
        onCollectionsScopeChange={setCollectionsScope}
        collections={collections}
        collectionsError={collectionsError}
      />
      <ExpirySelector value={expiry} onChange={setExpiry} />
      <ApiIssueList issues={issues} />
      <div style={{ display: "flex", gap: theme.space.s }}>
        <Button variant="primary" disabled={!valid || submitting} onClick={handleSubmit}>
          {submitting ? (isRotate ? "rotating…" : "creating…") : (isRotate ? "Rotate key" : "Create key")}
        </Button>
        <Button onClick={onCancel} disabled={submitting}>Cancel</Button>
      </div>
    </div>
  );
}
