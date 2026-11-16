// ====== Code Summary ======
// Strips the internal exception chain a job's raw `error` string carries (worker-side
// `PipelineRunError: pipeline run failed: admit (admission): ValueError: <useful message>`) down
// to the last useful segment — a user never needs the wrapper/step-name/exception-class prefix,
// only what actually went wrong.

// Matches a chain-segment header — an exception-class-shaped token ("ValueError", "PipelineRunError",
// optionally "Foo(bar)") immediately followed by ": ". Global + anchored so the LAST match's end
// marks where the useful tail begins; everything before it is wrapper/step-name noise.
const ERROR_CHAIN_RE = /(?:^|: )[A-Za-z][A-Za-z0-9]*(?:Error|Exception)(?:\([^)]*\))?: /g;

/** Keeps only the tail after the last recognized exception-class prefix in a chained error string —
 *  returns `raw` unchanged when no such prefix is found (already a plain message). */
export function humanizeJobError(raw: string): string {
  ERROR_CHAIN_RE.lastIndex = 0;
  let lastEnd = 0;
  let match: RegExpExecArray | null;
  while ((match = ERROR_CHAIN_RE.exec(raw)) !== null) {
    lastEnd = match.index + match[0].length;
  }
  return lastEnd > 0 ? raw.slice(lastEnd) : raw;
}
