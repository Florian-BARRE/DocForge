// ====== Code Summary ======
// ChainGateDisplay — visual gate connector shown between provider cards in ChainLadder.
// Renders the escalation trigger conditions (min_score, max_duration_ms) as a compact
// labeled pill between two providers, making the fallback semantics visible at a glance.
// Pure presentational component; all values come from props.

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChainGateDisplayProps {
  /** Score threshold below which the attempt escalates (default 0.5). */
  minScore: number
  /** Per-attempt wall-clock budget in ms; null means disabled. */
  maxDurationMs: number | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Compact visual connector showing the escalation conditions between two ladder steps.
 *
 * Reads the gate's min_score and optional max_duration_ms and renders them as a
 * pill label between a vertical stem, giving the user an at-a-glance understanding
 * of when the engine escalates from one provider to the next.
 *
 * Args:
 *   minScore:      Escalation score threshold (current gate value).
 *   maxDurationMs: Per-attempt timeout in ms, or null when disabled.
 */
export function ChainGateDisplay({ minScore, maxDurationMs }: ChainGateDisplayProps) {
  // 1. Build the condition label: score threshold + optional timeout.
  const scorePart = `score < ${minScore}`
  const timePart  = maxDurationMs != null ? ` · >${maxDurationMs}ms` : ''
  const label     = `${scorePart}${timePart} → escalate`

  return (
    <div className="chain-gate-display" aria-label={`Gate: ${label}`}>
      {/* Upper vertical stem */}
      <div className="chain-gate-stem" />

      {/* Gate condition pill */}
      <span className="chain-gate-pill" title={label}>
        {label}
      </span>

      {/* Lower vertical stem */}
      <div className="chain-gate-stem" />
    </div>
  )
}
