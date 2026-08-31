// ====== Code Summary ======
// Small display helpers for the export/import progress UI — byte-size formatting for the mono
// machine-value badge shown once a bundle is produced.

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
