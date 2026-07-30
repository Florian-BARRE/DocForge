// ====== Code Summary ======
// The document's landing tab — its own parse-time facts plus the full resolved metadata table
// (declared + generated values, each tagged with who filled it).

import type { DocumentDetail } from "../../../api/explorer";
import { theme } from "../../../theme";
import { MetadataTable } from "../metadata/MetadataTable";
import { FactsGrid } from "./FactsGrid";

const sectionStyle: React.CSSProperties = {
  background: theme.color.surface, border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600,
  color: theme.color.text, marginBottom: theme.space.m,
};

export function OverviewTab({ document }: { document: DocumentDetail }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Facts</h2>
        <FactsGrid document={document} />
      </section>
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Metadata</h2>
        <MetadataTable metadata={document.metadata} />
      </section>
    </div>
  );
}
