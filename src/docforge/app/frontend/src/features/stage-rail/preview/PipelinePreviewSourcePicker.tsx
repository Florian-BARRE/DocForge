// ====== Code Summary ======
// Picks WHAT the dry-run previews: an existing document already in the collection, or a freshly
// uploaded one (never ingested). Mirrors CostEstimatePanel's own TabNav-driven scope picker so the
// two "run a dry pass over this collection" panels read as the same idiom.

import type { DocumentGridRow } from "../../../api/corpus";
import { FileInputButton } from "../../../components/FileInputButton";
import { TabNav } from "../../../components/TabNav";
import { theme as t } from "../../../theme";
import { PipelineDocumentPicker } from "./PipelineDocumentPicker";

export type PreviewSourceMode = "document" | "upload";

const MODE_TABS = [
  { key: "document" as const, label: "Existing document" },
  { key: "upload" as const, label: "Upload a file" },
];

interface PipelinePreviewSourcePickerProps {
  collectionId: string;
  mode: PreviewSourceMode;
  onModeChange: (mode: PreviewSourceMode) => void;
  selectedDocument: DocumentGridRow | null;
  onSelectDocument: (doc: DocumentGridRow) => void;
  file: File | null;
  onFileSelected: (file: File | null) => void;
}

export function PipelinePreviewSourcePicker({
  collectionId, mode, onModeChange, selectedDocument, onSelectDocument, file, onFileSelected,
}: PipelinePreviewSourcePickerProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
      <TabNav tabs={MODE_TABS} active={mode} onSelect={onModeChange} navId="preview-source-mode" ariaLabel="Preview source" role="group" />
      {mode === "document" ? (
        <PipelineDocumentPicker collectionId={collectionId} selectedId={selectedDocument?.id ?? null} onSelect={onSelectDocument} />
      ) : (
        <FileInputButton
          label="Choose file"
          selectedText={file?.name ?? null}
          onFilesSelected={(files) => onFileSelected(files?.[0] ?? null)}
        />
      )}
    </div>
  );
}
