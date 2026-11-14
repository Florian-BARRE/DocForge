// ====== Code Summary ======
// Shared display formatters of the frontend — byte sizes and date-times. One source of truth for
// what each feature slice used to copy locally (explorer, corpus, estimate, transfer).

/** Human-readable byte size (binary units), e.g. `21.4 MB` — rendered in mono as a machine value. */
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

/** Locale date-time of an ISO timestamp, or an em dash when absent. */
export function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}
