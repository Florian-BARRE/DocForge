// ====== Code Summary ======
// The corpus toolbar's "Estimate cost" trigger — projects the ingest cost of exactly what the grid
// is currently showing: the hand-ticked selection when one exists, otherwise the active column
// filters (or the whole collection when neither is set). Opens CorpusEstimateDialog on click; the
// dialog owns the actual fetch + rendering.

import { useState } from "react";
import type { DocumentFilter, DocumentSelector } from "../../api/corpus";
import { Button } from "../../components/Button";
import { CorpusEstimateDialog } from "./CorpusEstimateDialog";
import { toEstimateSubset } from "./estimateSubset";

interface CorpusEstimateActionProps {
  collectionId: string;
  filter: DocumentFilter;
  selector: DocumentSelector;
  selectedCount: number;
  totalCount: number;
}

function subjectLabel(hasSelection: boolean, hasFilter: boolean, selectedCount: number, totalCount: number): string {
  if (hasSelection) return `${selectedCount.toLocaleString()} selected document${selectedCount === 1 ? "" : "s"}`;
  if (hasFilter) return `the ${totalCount.toLocaleString()} document${totalCount === 1 ? "" : "s"} matching the current filters`;
  return `the whole collection (${totalCount.toLocaleString()} document${totalCount === 1 ? "" : "s"})`;
}

export function CorpusEstimateAction({ collectionId, filter, selector, selectedCount, totalCount }: CorpusEstimateActionProps) {
  const [open, setOpen] = useState(false);
  const hasSelection = selectedCount > 0 && "document_ids" in selector && !!selector.document_ids;
  const hasFilter = Object.keys(filter).length > 0;

  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        {hasSelection ? `Estimate selected (${selectedCount.toLocaleString()})` : "Estimate cost"}
      </Button>
      {open && (
        <CorpusEstimateDialog
          collectionId={collectionId}
          subset={toEstimateSubset(selector, filter)}
          subjectLabel={subjectLabel(hasSelection, hasFilter, selectedCount, totalCount)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
