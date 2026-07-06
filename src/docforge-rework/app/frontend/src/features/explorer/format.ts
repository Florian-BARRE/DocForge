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

/** The API's page/block page numbers are observed 0-based on the wire; shown as 1-based here. */
export function displayPage(pageNumber: number): number {
  return pageNumber + 1;
}
