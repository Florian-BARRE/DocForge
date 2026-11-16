// ====== Code Summary ======
// Small helpers shared across the document explorer's pages/tabs — the document display name and
// the API's page numbering surfaced as a friendly 1-based page label (byte sizes and dates live in
// utils/format.ts).

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
