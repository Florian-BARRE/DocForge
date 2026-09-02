// ====== Code Summary ======
// The upload panel embedded in the collection detail page: a (multi-)file picker + a metadata form
// generated from the collection's user-origin, document-scope fields (the only ones a caller
// declares at upload time — system fields are pipeline-extracted, generated ones are metagen's,
// chunk-scope fields don't exist yet at document admission). Files are uploaded one at a time by
// looping the single-file endpoint (the backend dedups by content, so a client loop is safe); one
// file failing never blocks the rest, and each file's progress is shown inline.

import { useState } from "react";
import type { FieldSpec } from "../../api/collections";
import { HttpError, type ApiIssue } from "../../api/http";
import { uploadDocument } from "../../api/documents";
import { ApiIssueList } from "../../components/ApiIssueList";
import { Button } from "../../components/Button";
import { FileInputButton } from "../../components/FileInputButton";
import { FormField } from "../../components/FormField";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { MetadataFieldInput } from "./MetadataFieldInput";

type FileStatus = "queued" | "uploading" | "done" | "duplicate" | "failed";

interface FileEntry {
  file: File;
  status: FileStatus;
  detail: string | null;
}

const STATUS_TONE: Record<FileStatus, keyof typeof toneColor> = {
  queued: "dim",
  uploading: "accent",
  done: "ok",
  duplicate: "warn",
  failed: "error",
};

// Kept as a lookup so every status colour still resolves to a theme token (never a hardcoded value).
const toneColor = {
  dim: theme.color.dim,
  accent: theme.color.accent,
  ok: theme.color.ok,
  warn: theme.color.warn,
  error: theme.color.error,
} as const;

const STATUS_LABEL: Record<FileStatus, string> = {
  queued: "queued",
  uploading: "uploading…",
  done: "done",
  duplicate: "already ingested",
  failed: "failed",
};

interface UploadPanelProps {
  collectionId: string;
  fields: FieldSpec[];
  /** Called once the batch settles with at least one job launched. `lastJobId` is that batch's most
   *  recently launched job; `launchedCount` is how many — callers land on that job's own detail page
   *  for a single upload, or the collection's job list (filtered) once N>1, so a multi-file batch
   *  doesn't hide every job but the last one behind the Jobs tab. */
  onUploaded: (lastJobId: string, launchedCount: number) => void;
}

export function UploadPanel({ collectionId, fields, onUploaded }: UploadPanelProps) {
  const toast = useToast();
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [uploading, setUploading] = useState(false);
  const [issues, setIssues] = useState<ApiIssue[]>([]);

  const declarable = fields.filter((f) => f.origin === "user" && f.scope === "document");

  const setEntryAt = (index: number, patch: Partial<FileEntry>) =>
    setEntries((prev) => prev.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)));

  const onPick = (files: FileList | null) => {
    setIssues([]);
    setEntries(files ? Array.from(files).map((file) => ({ file, status: "queued", detail: null })) : []);
  };

  const handleUpload = async () => {
    if (!entries.length) return;
    setUploading(true);
    setIssues([]);

    // Only send fields the caller actually filled in — the pipeline enforces `required`. Built once;
    // every file in the batch is admitted with the same declared metadata.
    const metadata: Record<string, unknown> = {};
    for (const field of declarable) {
      const value = values[field.field_name];
      if (value === undefined || value === "") continue;
      metadata[field.field_name] = value;
    }

    let lastJobId: string | null = null;
    let succeeded = 0;
    let failed = 0;

    // Sequential loop: one file's failure must not abort the rest, so each is caught in isolation.
    for (let index = 0; index < entries.length; index += 1) {
      const { file } = entries[index];
      setEntryAt(index, { status: "uploading", detail: null });
      try {
        const result = await uploadDocument({ file, collectionId, metadata });
        if (result.duplicate) {
          setEntryAt(index, { status: "duplicate", detail: `already ingested as ${result.document_id.slice(0, 8)}` });
        } else {
          setEntryAt(index, { status: "done", detail: null });
          lastJobId = result.job_id;
          succeeded += 1;
        }
      } catch (error) {
        failed += 1;
        const message = error instanceof HttpError ? error.message : String(error);
        setEntryAt(index, { status: "failed", detail: message });
      }
    }

    setUploading(false);
    if (failed > 0) toast.error(`${failed} of ${entries.length} file(s) failed to upload`);
    else if (succeeded > 0) toast.success(`Ingestion launched — ${succeeded} file(s)`);
    else toast.info("Nothing ingested — every file was a duplicate");
    // A single file lands the caller on that one job's own detail page; a batch lands on the
    // collection's job list instead, so all N launched jobs stay reachable (not just the last one).
    if (lastJobId) onUploaded(lastJobId, succeeded);
  };

  const doneCount = entries.filter((e) => e.status === "done" || e.status === "duplicate").length;
  const failedCount = entries.filter((e) => e.status === "failed").length;

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m, width: "100%",
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
      }}
    >
      <FormField label="Files">
        <FileInputButton
          label={entries.length > 1 ? "Choose files" : "Choose file"}
          multiple
          selectedText={entries.length ? `${entries.length} file${entries.length === 1 ? "" : "s"} selected` : null}
          onFilesSelected={onPick}
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

      {entries.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
          {entries.map((entry, index) => (
            <div
              key={index}
              style={{
                display: "flex", alignItems: "center", gap: theme.space.s,
                fontSize: theme.font.size.s, color: theme.color.text,
                borderTop: index === 0 ? undefined : `1px solid ${theme.color.line}`,
                paddingTop: index === 0 ? 0 : theme.space.xs,
              }}
            >
              <span style={{ flex: 1, wordBreak: "break-all" }}>{entry.file.name}</span>
              <span style={{ color: toneColor[STATUS_TONE[entry.status]], fontSize: theme.font.size.xs, whiteSpace: "nowrap" }}>
                {STATUS_LABEL[entry.status]}
              </span>
              {entry.detail && (
                <span
                  style={{ color: theme.color.dim, fontSize: theme.font.size.xs, fontFamily: theme.font.mono, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={entry.detail}
                >
                  {entry.detail}
                </span>
              )}
            </div>
          ))}
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, marginTop: theme.space.xs }}>
            {doneCount}/{entries.length} processed{failedCount > 0 ? ` · ${failedCount} failed` : ""}
          </div>
        </div>
      )}

      <ApiIssueList issues={issues} />
      <div>
        <Button variant="primary" disabled={!entries.length || uploading} onClick={handleUpload}>
          {uploading ? "uploading…" : entries.length > 1 ? `Upload ${entries.length} files` : "Upload"}
        </Button>
      </div>
    </div>
  );
}
