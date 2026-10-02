// ====== Code Summary ======
// The document Overview's "Metadata" panel: the read-only resolved table by default, switching to a
// schema-driven editor (document-scope USER/GENERATED fields) behind an Edit button. Save PATCHes only
// the changed values — no re-ingest — and reports instant "Saved" or a live re-embed indicator.

import type { FieldSpec } from "../../../../api/collections";
import type { MetadataValue } from "../../../../api/explorer";
import { Button } from "../../../../components/Button";
import type { Navigate } from "../../../../shell/view";
import { theme } from "../../../../theme";
import { MetadataTable } from "../MetadataTable";
import { MetadataEditField } from "./MetadataEditField";
import type { DraftValues } from "./metadataDraft";
import { ReembedStatus } from "./ReembedStatus";
import { useMetadataEditor } from "./useMetadataEditor";

interface MetadataSectionProps {
  documentId: string;
  collectionId: string;
  metadata: MetadataValue[];
  onNavigate: Navigate;
  /** Lets the page fold the saved values back into its DocumentDetail so the table reflects them. */
  onSaved: (updated: DraftValues, specs: FieldSpec[]) => void;
}

const noteStyle: React.CSSProperties = { color: theme.color.dim, fontSize: theme.font.size.xs };

export function MetadataSection({ documentId, collectionId, metadata, onNavigate, onSaved }: MetadataSectionProps) {
  const editor = useMetadataEditor(documentId, collectionId, metadata, onSaved);
  const canEdit = editor.loaded && editor.editable.length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m, flexWrap: "wrap" }}>
        {editor.result && !editor.editing ? (
          <ReembedStatus result={editor.result} collectionId={collectionId} onNavigate={onNavigate} />
        ) : <span />}
        {canEdit && !editor.editing && <Button size="sm" variant="secondary" onClick={editor.startEdit}>Edit values</Button>}
      </div>

      {!editor.editing && <MetadataTable metadata={metadata} />}

      {editor.editing && (
        <form
          onSubmit={(e) => { e.preventDefault(); void editor.save(); }}
          style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}
        >
          {editor.editable.map((field) => (
            <MetadataEditField
              key={field.field_name}
              field={field}
              value={editor.draft[field.field_name]}
              error={editor.fieldErrors[field.field_name]}
              onChange={(value) => editor.setValue(field.field_name, value)}
            />
          ))}
          {editor.generalErrors.map((message) => (
            <div key={message} role="alert" style={{ color: theme.color.errorStrong, fontSize: theme.font.size.s }}>{message}</div>
          ))}
          <div style={{ display: "flex", gap: theme.space.s }}>
            <Button type="submit" variant="primary" size="sm" disabled={!editor.dirty || editor.saving}>
              {editor.saving ? "Saving…" : "Save changes"}
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={editor.cancel} disabled={editor.saving}>Cancel</Button>
          </div>
        </form>
      )}

      {editor.editing && editor.readOnlyChunkFields.length > 0 && (
        <span style={noteStyle}>
          Per-chunk fields ({editor.readOnlyChunkFields.map((f) => f.field_name).join(", ")}) are set on each chunk and need a reindex to change — not editable here.
        </span>
      )}
    </div>
  );
}
