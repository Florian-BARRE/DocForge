// ====== Code Summary ======
// The collection export panel — mirrors UploadPanel's inline-card placement under the collection
// header (CollectionShell owns the show/hide toggle). A SCOPE selector picks between the whole
// collection (the existing async `.dcexport` flow, unchanged — ExportCollectionSection) and a
// single config slice (the synchronous `.dfsnippet` flow — ExportSnippetSection, which also carries
// the "Apply snippet" import affordance).

import { useState } from "react";
import { TabNav } from "../../../components/TabNav";
import { theme } from "../../../theme";
import { ExportCollectionSection } from "./ExportCollectionSection";
import { ExportSnippetSection } from "./ExportSnippetSection";

interface ExportPanelProps {
  collectionId: string;
  collectionName: string;
}

type ExportScope = "collection" | "snippet";

const SCOPE_TABS: { key: ExportScope; label: string }[] = [
  { key: "collection", label: "Whole collection" },
  { key: "snippet", label: "Config snippet" },
];

export function ExportPanel({ collectionId, collectionName }: ExportPanelProps) {
  const [scope, setScope] = useState<ExportScope>("collection");

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m, width: "100%", maxWidth: 460,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
      }}
    >
      <div>
        <div style={{ fontSize: theme.font.size.l, fontWeight: 700, color: theme.color.text }}>Export collection</div>
      </div>

      <TabNav tabs={SCOPE_TABS} active={scope} onSelect={setScope} navId="export-scope" ariaLabel="Export scope" role="group" />

      {scope === "collection" ? (
        <ExportCollectionSection collectionId={collectionId} collectionName={collectionName} />
      ) : (
        <ExportSnippetSection collectionId={collectionId} collectionName={collectionName} />
      )}
    </div>
  );
}
