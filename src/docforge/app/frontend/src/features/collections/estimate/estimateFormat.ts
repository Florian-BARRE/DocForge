// ====== Code Summary ======
// Small formatting helpers local to the cost-estimate panel — byte sizes, adaptive USD amounts,
// and assumption-key humanizing. `formatBytes` is a deliberate duplicate of
// features/explorer/format.ts (feature slices never cross-import, even for tiny pure helpers —
// see agent-memory/frontend/feature_slice_isolation.md).

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

/** Sub-cent per-call/per-document rates are common for LLM pricing — fall back to 4 decimals so
 *  they don't all collapse to "$0.00". */
export function formatUsd(value: number): string {
  if (value === 0) return "$0.00";
  const decimals = Math.abs(value) < 0.01 ? 4 : 2;
  return `$${value.toFixed(decimals)}`;
}

/** Turns a backend assumption key like `avg_tokens_per_page` into "Avg tokens per page". */
export function humanizeAssumptionKey(key: string): string {
  const words = key.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
