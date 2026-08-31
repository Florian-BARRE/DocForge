// ====== Code Summary ======
// Small formatting helpers local to the corpus grid — byte sizes and dates. A deliberate
// duplicate of features/explorer/format.ts (feature slices never cross-import, even for tiny
// pure helpers — see agent-memory/frontend/feature_slice_isolation.md).

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
