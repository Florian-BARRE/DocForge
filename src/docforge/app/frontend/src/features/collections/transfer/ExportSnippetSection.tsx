// ====== Code Summary ======
// The config-SNIPPET half of the export panel — a granular, synchronous alternative to the whole
// `.dcexport` bundle: pick which slice (ingestion pipeline / search pipeline / metadata schema),
// export it as a small `.dfsnippet` (a plain GET → download, no ExportProgress polling — the export
// is instant), then optionally apply an inbound snippet of the SAME kind back onto this collection.

import { useState } from "react";
import { getSnippet, type SnippetKind } from "../../../api/snippets";
import { Button } from "../../../components/Button";
import { TabNav } from "../../../components/TabNav";
import { theme } from "../../../theme";
import { ApplySnippetForm } from "./ApplySnippetForm";
import { downloadSnippet, snippetFilename, SNIPPET_KIND_LABEL } from "./snippetFormat";

interface ExportSnippetSectionProps {
  collectionId: string;
  collectionName: string;
}

const KIND_TABS: { key: SnippetKind; label: string }[] = [
  { key: "pipeline", label: SNIPPET_KIND_LABEL.pipeline },
  { key: "search", label: SNIPPET_KIND_LABEL.search },
  { key: "schema", label: SNIPPET_KIND_LABEL.schema },
];

export function ExportSnippetSection({ collectionId, collectionName }: ExportSnippetSectionProps) {
  const [kind, setKind] = useState<SnippetKind>("pipeline");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportSnippet = async () => {
    setExporting(true);
    setError(null);
    try {
      const snippet = await getSnippet(collectionId, kind);
      downloadSnippet(snippet, snippetFilename(collectionName, kind));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
        A single config slice, secret-masked and versioned — for sharing or reusing just the pipeline,
        the search setup, or the metadata schema, without the data. Saved as a{" "}
        <span style={{ fontFamily: theme.font.mono }}>.dfsnippet</span> file.
      </div>

      <TabNav tabs={KIND_TABS} active={kind} onSelect={setKind} navId="export-snippet-kind" ariaLabel="Config slice" role="group" />

      <div>
        <Button variant="secondary" disabled={exporting} onClick={exportSnippet}>
          {exporting ? "preparing…" : `Export ${SNIPPET_KIND_LABEL[kind].toLowerCase()}`}
        </Button>
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}

      <ApplySnippetForm collectionId={collectionId} kind={kind} />
    </div>
  );
}
