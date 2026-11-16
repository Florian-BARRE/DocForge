// ====== Code Summary ======
// Small formatting helpers local to the cost-estimate panel — adaptive USD amounts and
// assumption-key humanizing (byte sizes live in utils/format.ts).

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
