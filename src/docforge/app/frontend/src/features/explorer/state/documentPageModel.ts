// ====== Code Summary ======
// Pure constants/derivations of the document page (DocumentPage / useDocumentPage): the tab list
// and the page width per tab. No React.

import type { DocumentTabKey } from "./useDocumentTabs";

// The former "Overview"/collection-shell-tab collision is gone (collection nav now lives in the
// persistent rail, not in this shell), so the document's own landing tab can be "Overview" again
// (still the same facts+metadata content; see OverviewTab.tsx).
export const TABS: { key: DocumentTabKey; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "pages", label: "Pages" },
  { key: "layout", label: "Layout" },
  { key: "ir", label: "IR" },
  { key: "chunks", label: "Chunks" },
  { key: "trace", label: "Trace" },
];

/** The Layout tab gets a wider column (three lanes side by side); every other tab stays narrow. */
export function pageMaxWidthOf(activeTab: DocumentTabKey): number {
  return activeTab === "layout" ? 1560 : 1200;
}
