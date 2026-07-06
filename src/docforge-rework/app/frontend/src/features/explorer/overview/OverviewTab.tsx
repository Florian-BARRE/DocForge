// ====== Code Summary ======
// The document's landing tab — its own parse-time facts plus the full resolved metadata table
// (declared + generated values, each tagged with who filled it).

import type { DocumentDetail } from "../../../api/explorer";
import { theme } from "../../../theme";
import { MetadataTable } from "../metadata/MetadataTable";
import { FactsGrid } from "./FactsGrid";

export function OverviewTab({ document }: { document: DocumentDetail }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <section>
        <h2 style={{ fontSize: theme.font.size.l, marginBottom: theme.space.s }}>Facts</h2>
        <FactsGrid document={document} />
      </section>
      <section>
        <h2 style={{ fontSize: theme.font.size.l, marginBottom: theme.space.s }}>Metadata</h2>
        <MetadataTable metadata={document.metadata} />
      </section>
    </div>
  );
}
