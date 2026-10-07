// ====== Code Summary ======
// Small formatting helpers shared across the document explorer's pages/tabs — byte sizes, dates
// and the API's page numbering surfaced as a friendly 1-based page label.

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

export function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

/** The title a human should see for a document: the collection's title_field value, else the parsed
 *  title, else the filename. */
export function documentDisplayName(doc: { display_title?: string | null; title?: string | null; filename: string }): string {
  return doc.display_title || doc.title || doc.filename;
}

/** The 1-based page a reader sees for a page row (falls back for a pre-0.23 server without page_label). */
export function pageLabelOf(page: { page_number: number; page_label?: number | null }): number {
  return page.page_label ?? page.page_number + 1;
}

/** The 1-based page a reader sees for an IR block (falls back for a pre-0.23 server). */
export function blockPageNumberOf(block: { page: number; page_number?: number | null }): number {
  return block.page_number ?? block.page + 1;
}
