// ====== Code Summary ======
// The upload panel embedded in the collection detail page: a file picker + a metadata form
// generated from the collection's user-origin, document-scope fields (the only ones a caller
// declares at upload time — system fields are pipeline-extracted, generated ones are metagen's,
// chunk-scope fields don't exist yet at document admission).

import { useState } from "react";
import type { FieldSpec } from "../../api/collections";
import { HttpError, type ApiIssue } from "../../api/http";
import { uploadDocument } from "../../api/documents";
import { ApiIssueList } from "../../components/ApiIssueList";
import { Button } from "../../components/Button";
import { FormField } from "../../components/FormField";
import { theme } from "../../theme";
import { MetadataFieldInput } from "./MetadataFieldInput";

interface UploadPanelProps {
  collectionId: string;
  fields: FieldSpec[];
  onUploaded: (jobId: string) => void;
}

export function UploadPanel({ collectionId, fields, onUploaded }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [uploading, setUploading] = useState(false);
  const [issues, setIssues] = useState<ApiIssue[]>([]);
  const [duplicateNotice, setDuplicateNotice] = useState<string | null>(null);

  const declarable = fields.filter((f) => f.origin === "user" && f.scope === "document");

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setIssues([]);
    setDuplicateNotice(null);
    try {
      // Only send fields the caller actually filled in — the pipeline enforces `required`.
      const metadata: Record<string, unknown> = {};
      for (const field of declarable) {
        const value = values[field.field_name];
        if (value === undefined || value === "") continue;
        metadata[field.field_name] = value;
      }
      const result = await uploadDocument({ file, collectionId, metadata });
      if (result.duplicate) setDuplicateNotice(`Identical content already ingested as document ${result.document_id}.`);
      else onUploaded(result.job_id);
    } catch (error) {
      setIssues(error instanceof HttpError ? error.issues : [{ message: String(error) }]);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m, width: "100%",
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
      }}
    >
      <FormField label="File">
        <input
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          style={{ fontSize: theme.font.size.s, color: theme.color.text }}
        />
      </FormField>
      {declarable.map((field) => (
        <MetadataFieldInput
          key={field.field_name}
          field={field}
          value={values[field.field_name]}
          onChange={(value) => setValues((v) => ({ ...v, [field.field_name]: value }))}
        />
      ))}
      {duplicateNotice && <div style={{ color: theme.color.warn, fontSize: theme.font.size.s }}>{duplicateNotice}</div>}
      <ApiIssueList issues={issues} />
      <div>
        <Button variant="primary" disabled={!file || uploading} onClick={handleUpload}>
          {uploading ? "uploading…" : "Upload"}
        </Button>
      </div>
    </div>
  );
}
