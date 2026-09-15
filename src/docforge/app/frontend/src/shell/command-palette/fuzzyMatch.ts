// ====== Code Summary ======
// Minimal, dependency-free fuzzy scorer for the command palette. No fuzzy-search library exists in
// this app's dependency tree (package.json) and pulling one in for a handful of short labels
// (collection names, nav destinations, action names) would be disproportionate.

/**
 * Score how well `query` matches `target` (case-insensitive).
 *
 * A contiguous substring match scores by its start index (0 = prefix, the strongest match). A
 * non-contiguous subsequence match still counts but always ranks behind any substring match (offset
 * into the 1000s). Returns null when `query` isn't even a subsequence of `target`.
 */
export function fuzzyScore(query: string, target: string): number | null {
  const q = query.trim().toLowerCase();
  if (!q) return 0;
  const t = target.toLowerCase();

  const substringIndex = t.indexOf(q);
  if (substringIndex !== -1) return substringIndex;

  let cursor = 0;
  let gap = 0;
  for (const char of q) {
    const found = t.indexOf(char, cursor);
    if (found === -1) return null;
    gap += found - cursor;
    cursor = found + 1;
  }
  return 1000 + gap;
}
