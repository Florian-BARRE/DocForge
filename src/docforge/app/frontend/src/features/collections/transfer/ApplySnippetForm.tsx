// ====== Code Summary ======
// Uploads a `.dfsnippet` file and applies it onto THIS collection via the matching-kind POST — the
// import half of the config-snippet round trip. Synchronous (no transfer/polling): the backend
// validates the format version + kind match and reports whether the change now needs a reindex.

import { useState } from "react";
import { HttpError } from "../../../api/http";
import { applySnippet, type CollectionSnippet, type SnippetKind } from "../../../api/snippets";
import { Button } from "../../../components/Button";
import { FileInputButton } from "../../../components/FileInputButton";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { SNIPPET_KIND_LABEL } from "./snippetFormat";

interface ApplySnippetFormProps {
  collectionId: string;
  /** The slice this form applies onto — must match the uploaded file's own `kind` (422 otherwise). */
  kind: SnippetKind;
}

export function ApplySnippetForm({ collectionId, kind }: ApplySnippetFormProps) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = async () => {
    if (!file) return;
    setApplying(true);
    setError(null);
    try {
      const text = await file.text();
      let snippet: CollectionSnippet;
      try {
        snippet = JSON.parse(text) as CollectionSnippet;
      } catch {
        throw new Error("That file isn't valid JSON — is it really a .dfsnippet?");
      }
      const result = await applySnippet(collectionId, kind, snippet);
      toast.success(
        result.needs_reindex
          ? `${SNIPPET_KIND_LABEL[kind]} snippet applied — this collection now needs a reindex.`
          : `${SNIPPET_KIND_LABEL[kind]} snippet applied.`,
      );
      setFile(null);
    } catch (e) {
      setError(e instanceof HttpError ? e.message : e instanceof Error ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s, borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.m }}>
      <div style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
        Apply a <span style={{ fontFamily: theme.font.mono }}>.dfsnippet</span> onto this collection's{" "}
        {SNIPPET_KIND_LABEL[kind].toLowerCase()}, replacing it.
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
        <FileInputButton
          label="Choose file"
          selectedText={file?.name ?? null}
          accept=".dfsnippet"
          disabled={applying}
          onFilesSelected={(files) => setFile(files?.[0] ?? null)}
        />
        <Button size="sm" variant="secondary" disabled={!file || applying} onClick={apply}>
          {applying ? "applying…" : "Apply snippet"}
        </Button>
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
    </div>
  );
}
