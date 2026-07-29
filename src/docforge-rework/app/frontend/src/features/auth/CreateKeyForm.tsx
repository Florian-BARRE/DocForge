// ====== Code Summary ======
// The "new key" form — name + permissions builder, submits via `createKey`. The plaintext result
// is handed to the parent (AuthKeysPage), which owns the one-time reveal modal and the list
// refresh; this form never keeps a copy of it.

import { useEffect, useState } from "react";
import { createKey, type ApiCapability, type CreatedApiKey } from "../../api/auth";
import { listCollections, type Collection } from "../../api/collections";
import type { ApiIssue } from "../../api/http";
import { HttpError } from "../../api/http";
import { ApiIssueList } from "../../components/ApiIssueList";
import { Button } from "../../components/Button";
import { FormField } from "../../components/FormField";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";
import { PermissionsBuilder, type CollectionsScope } from "./PermissionsBuilder";

interface CreateKeyFormProps {
  onCreated: (createdKey: CreatedApiKey) => void;
  onCancel: () => void;
}

export function CreateKeyForm({ onCreated, onCancel }: CreateKeyFormProps) {
  const [name, setName] = useState("");
  const [fullAccess, setFullAccess] = useState(true);
  const [capabilities, setCapabilities] = useState<ApiCapability[]>(["read"]);
  const [collectionsScope, setCollectionsScope] = useState<CollectionsScope>("all");
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
  const valid = name.trim().length > 0 && scopedValid;

  const handleSubmit = async () => {
    setSubmitting(true);
    setIssues([]);
    try {
      const created = await createKey({
        name: name.trim(),
        permissions: fullAccess
          ? null
          : { capabilities, collections: collectionsScope === "all" ? ["*"] : collectionsScope },
      });
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
        New API key
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
      <ApiIssueList issues={issues} />
      <div style={{ display: "flex", gap: theme.space.s }}>
        <Button variant="primary" disabled={!valid || submitting} onClick={handleSubmit}>
          {submitting ? "creating…" : "Create key"}
        </Button>
        <Button onClick={onCancel} disabled={submitting}>Cancel</Button>
      </div>
    </div>
  );
}
