// ====== Code Summary ======
// The document's landing tab — the full "System metadata" picture (everything DocForge derives),
// the download/view actions, and the resolved metadata table (declared + generated values, each
// tagged with who filled it).

import type { DocumentDetail, PageInfo } from "../../../api/explorer";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";
import type { FieldSpec } from "../../../api/collections";
import { MetadataSection } from "../metadata/edit/MetadataSection";
import type { DraftValues } from "../metadata/edit/metadataDraft";
import { DocumentFailureBanner } from "./DocumentFailureBanner";
import { DownloadsPanel } from "./DownloadsPanel";
import { SystemMetadataPanel } from "./SystemMetadataPanel";

const sectionStyle: React.CSSProperties = {
  background: theme.color.surface, border: `1px solid ${theme.color.line}`,
  borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600,
  color: theme.color.text, marginBottom: theme.space.m,
};

interface OverviewTabProps {
  document: DocumentDetail;
  /** The document's page list — null until the overview tab has warmed it (see useDocumentTabs);
   *  SystemMetadataPanel degrades its page-derived facts gracefully while it's still null. */
  pages: PageInfo[] | null;
  collectionId: string;
  onNavigate: Navigate;
  /** Folds freshly-saved metadata values back into the loaded document (see DocumentPage). */
  onMetadataSaved: (updated: DraftValues, specs: FieldSpec[]) => void;
}

export function OverviewTab({ document, pages, collectionId, onNavigate, onMetadataSaved }: OverviewTabProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      <DocumentFailureBanner document={document} collectionId={collectionId} onNavigate={onNavigate} />
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>System metadata</h2>
        <SystemMetadataPanel document={document} pages={pages} />
      </section>
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Download &amp; view</h2>
        <DownloadsPanel document={document} />
      </section>
      <section style={sectionStyle}>
        <h2 style={sectionTitleStyle}>Metadata</h2>
        <MetadataSection
          documentId={document.id}
          collectionId={collectionId}
          metadata={document.metadata}
          onNavigate={onNavigate}
          onSaved={onMetadataSaved}
        />
      </section>
    </div>
  );
}
