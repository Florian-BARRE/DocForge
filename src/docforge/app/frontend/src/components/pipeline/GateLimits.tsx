// ====== Code Summary ======
// GateLimits — "Quality & limits" section in the chain ladder.
// Shows min_score and max_duration_ms as always-visible, clearly-labelled controls.
// max_duration_ms is converted to/from seconds for display (stored internally in ms).
// Previously hidden behind a "gate" toggle; now always visible to aid discoverability.

// ====== Internal Project Imports ======
import type { ConfigNode } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface GateLimitsProps {
  /** Gate child node for min_score (scalar, range 0–1). */
  minScoreNode: ConfigNode | undefined
  /** Gate child node for max_duration_ms (scalar int). */
  durationNode: ConfigNode | undefined
  /** Current min_score value (0 = off). */
  minScore: number
  /** Current max_duration_ms value in ms (null = disabled). */
  maxDurationMs: number | null
  /** Write accessor for absolute config dot-paths. */
  writeValue: (absPath: string, v: unknown) => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Convert milliseconds to a human-readable seconds value (1 decimal place).
 *
 * Args:
 *   ms: Duration in milliseconds.
 *
 * Returns:
 *   number: Duration in seconds, rounded to 1 decimal.
 */
function msToSec(ms: number): number {
  return Math.round(ms / 100) / 10
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Always-visible quality threshold and timeout controls for the chain gate.
 *
 * Replaces the old hidden "gate settings" toggle with a clearly-labelled section
 * so users can see and adjust escalation thresholds without hunting for a toggle.
 * Timeout is shown in seconds for readability but stored as milliseconds.
 *
 * Args:
 *   minScoreNode: ConfigNode for min_score (carries the absolute path for writes).
 *   durationNode: ConfigNode for max_duration_ms (carries the absolute path).
 *   minScore:     Current quality threshold (0 = score-based escalation off).
 *   maxDurationMs: Current per-attempt timeout in ms (null = no limit).
 *   writeValue:   Write accessor for absolute dot-paths.
 */
export function GateLimits({
  minScoreNode, durationNode, minScore, maxDurationMs, writeValue,
}: GateLimitsProps) {
  // Render nothing when neither gate field node is available.
  if (!minScoreNode && !durationNode) return null

  // Convert stored ms to seconds for the display input.
  const maxSec = maxDurationMs != null && maxDurationMs > 0
    ? msToSec(maxDurationMs)
    : null

  return (
    <div className="chain-section">
      {/* Section header */}
      <div className="chain-section-head">
        <span className="chain-section-title">Quality &amp; limits</span>
        <span className="chain-section-hint">
          Controls when to escalate from one provider to the next.
        </span>
      </div>

      <div className="gate-limits">
        {/* Minimum quality score — 0 means disabled */}
        {minScoreNode && (
          <div className="gate-limit-row">
            <label className="gate-limit-label" htmlFor="gate-min-score">
              Minimum quality score
              <span className="gate-limit-hint">
                {minScore > 0
                  ? `Escalate to the next provider if score is below ${minScore}`
                  : 'Off — never escalate based on score alone'}
              </span>
            </label>
            <input
              id="gate-min-score"
              className="input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={e => {
                const v = parseFloat(e.target.value)
                writeValue(minScoreNode.path, isNaN(v) ? 0 : Math.min(1, Math.max(0, v)))
              }}
              style={{ width: 90 }}
            />
          </div>
        )}

        {/* Per-attempt timeout — displayed in seconds, stored in ms */}
        {durationNode && (
          <div className="gate-limit-row">
            <label className="gate-limit-label" htmlFor="gate-max-duration">
              Timeout per attempt (s)
              <span className="gate-limit-hint">
                {maxSec != null
                  ? `Escalate after ${maxSec}s`
                  : 'Off — no time limit per provider attempt'}
              </span>
            </label>
            <input
              id="gate-max-duration"
              className="input"
              type="number"
              min={0}
              step={0.5}
              value={maxSec ?? ''}
              placeholder="off"
              onChange={e => {
                const v = parseFloat(e.target.value)
                // Convert seconds back to milliseconds for storage.
                writeValue(durationNode.path, isNaN(v) || v <= 0 ? null : Math.round(v * 1000))
              }}
              style={{ width: 90 }}
            />
          </div>
        )}
      </div>
    </div>
  )
}
