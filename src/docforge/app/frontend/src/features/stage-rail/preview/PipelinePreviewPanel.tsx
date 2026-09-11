// ====== Code Summary ======
// "Test on a sample" — the ingestion editor's dry-run panel. Pick a source (an existing document, or
// upload one fresh), run it against the CURRENT candidate blob (whatever the rail has on screen right
// now, saved or not — see usePipelinePreview's doc comment), and see the bounded report: IR summary +
// cost, the first chunks, and the full per-node trace. Nothing here is persisted; no ingestion runs.
// Mirrors CostEstimatePanel's card shell so both "dry-run this collection" panels read as one idiom.

import { useState } from "react";
import type { DocumentGridRow } from "../../../api/corpus";
import type { GroupBlob } from "../../../api/types";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { theme as t } from "../../../theme";
import { humanizePreviewError } from "./previewErrorHumanize";
import { PipelinePreviewChunks } from "./PipelinePreviewChunks";
import { PipelinePreviewSourcePicker, type PreviewSourceMode } from "./PipelinePreviewSourcePicker";
import { PipelinePreviewSummary } from "./PipelinePreviewSummary";
import { PipelinePreviewTrace } from "./PipelinePreviewTrace";
import { usePipelinePreview } from "./usePipelinePreview";

interface PipelinePreviewPanelProps {
  collectionId: string;
  /** The rail's current candidate blob — always sent as the override, see usePipelinePreview. */
  blob: GroupBlob;
}

function runLabel(status: string): string {
  if (status === "submitting") return "Submitting…";
  if (status === "pending") return "Queued…";
  if (status === "running") return "Running…";
  return "Run preview";
}

export function PipelinePreviewPanel({ collectionId, blob }: PipelinePreviewPanelProps) {
  const [mode, setMode] = useState<PreviewSourceMode>("document");
  const [selectedDocument, setSelectedDocument] = useState<DocumentGridRow | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const { status, result, error, run } = usePipelinePreview({ collectionId, blob });

  const busy = status === "submitting" || status === "pending" || status === "running";
  const canRun = mode === "document" ? selectedDocument !== null : file !== null;

  const handleRun = () => {
    if (mode === "document" && selectedDocument) run({ kind: "document", documentId: selectedDocument.id });
    if (mode === "upload" && file) run({ kind: "upload", file });
  };

  return (
    <div
      style={{
        background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l,
        boxShadow: t.shadow.sm, overflow: "hidden",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m, padding: `${t.space.m}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}` }}>
        <span style={{ fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xl, color: t.color.text }}>
          Test on a sample
        </span>
        <span style={{ color: t.color.dim, fontSize: t.font.size.s }}>
          Dry-run this pipeline on one document — nothing is saved, nothing is ingested.
        </span>
      </div>

      <div style={{ padding: t.space.l, display: "flex", flexDirection: "column", gap: t.space.l }}>
        <PipelinePreviewSourcePicker
          collectionId={collectionId}
          mode={mode}
          onModeChange={setMode}
          selectedDocument={selectedDocument}
          onSelectDocument={setSelectedDocument}
          file={file}
          onFileSelected={setFile}
        />
        <div>
          <Button variant="primary" onClick={handleRun} disabled={!canRun || busy}>
            {runLabel(status)}
          </Button>
        </div>

        {status === "failed" && error && <ErrorState message={humanizePreviewError(error)} onRetry={handleRun} />}
        {busy && <LoadingState label={`${runLabel(status).toLowerCase()} the dry-run…`} />}
        {status === "done" && result && (
          <div style={{ display: "flex", flexDirection: "column", gap: t.space.xl }}>
            <PipelinePreviewSummary result={result} />
            <section style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
              <h3 style={{ margin: 0, fontSize: t.font.size.m, color: t.color.text }}>
                Chunks ({result.chunks.length})
              </h3>
              <PipelinePreviewChunks chunks={result.chunks} />
            </section>
            <section style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
              <h3 style={{ margin: 0, fontSize: t.font.size.m, color: t.color.text }}>
                Execution trace ({result.trace.length})
              </h3>
              <PipelinePreviewTrace trace={result.trace} />
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
