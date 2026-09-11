// ====== Code Summary ======
// Strips the internal exception-chain prefix off a preview job's top-level `error`/`failed` string
// (worker-side `"PipelineRunError: ...: ValueError: <useful message>"`) down to the last useful
// segment. A LOCAL copy of `features/monitoring/jobErrorHumanize.ts`'s regex — deliberately not
// cross-imported (feature slices stay independently movable, see agent-memory/frontend
// feature_slice_isolation.md); this is the one small pure helper, not a growing shared module.

const ERROR_CHAIN_RE = /(?:^|: )[A-Za-z][A-Za-z0-9]*(?:Error|Exception)(?:\([^)]*\))?: /g;

/** Keeps only the tail after the last recognized exception-class prefix in a chained error string —
 *  returns `raw` unchanged when no such prefix is found (already a plain message). */
export function humanizePreviewError(raw: string): string {
  ERROR_CHAIN_RE.lastIndex = 0;
  let lastEnd = 0;
  let match: RegExpExecArray | null;
  while ((match = ERROR_CHAIN_RE.exec(raw)) !== null) {
    lastEnd = match.index + match[0].length;
  }
  return lastEnd > 0 ? raw.slice(lastEnd) : raw;
}
