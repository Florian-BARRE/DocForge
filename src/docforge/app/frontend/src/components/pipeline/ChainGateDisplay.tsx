// ====== Code Summary ======
// ChainGateDisplay — plain-language fallback connector between provider cards.
// Replaces technical shorthand ("score < 0.5 · >5000ms → escalate") with
// readable prose so first-time users understand the escalation semantics.
// Pure presentational component; all values come from props.

// ── Types ─────────────────────────────────────────────────────────────────────

interface ChainGateDisplayProps {
  /** Score threshold below which the attempt escalates (0 = score-based escalation off). */
  minScore: number
  /** Per-attempt wall-clock budget in ms; null means disabled. */
  maxDurationMs: number | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Plain-language connector shown between consecutive provider cards in the ladder.
 *
 * Builds a short prose sentence like "falls back if it errors or scores below 0.5"
 * instead of the old terse notation so the escalation intent is obvious.
 *
 * Args:
 *   minScore:      Escalation score threshold (0 = score-based escalation disabled).
 *   maxDurationMs: Per-attempt timeout in ms, or null when disabled.
 */
export function ChainGateDisplay({ minScore, maxDurationMs }: ChainGateDisplayProps) {
  // 1. Build a human-readable list of conditions that trigger escalation.
  const conditions: string[] = []
  if (minScore > 0) conditions.push(`scores below ${minScore}`)
  if (maxDurationMs != null && maxDurationMs > 0) conditions.push('times out')

  const conditionText = conditions.length > 0
    ? `falls back if it errors or ${conditions.join(' or ')}`
    : 'falls back if it errors'

  return (
    <div className="chain-gate-display" aria-label={conditionText}>
      {/* Upper vertical stem */}
      <div className="chain-gate-stem" />

      {/* Plain-language fallback condition pill */}
      <span className="chain-gate-pill" title={conditionText}>
        {conditionText}
      </span>

      {/* Lower vertical stem */}
      <div className="chain-gate-stem" />
    </div>
  )
}
