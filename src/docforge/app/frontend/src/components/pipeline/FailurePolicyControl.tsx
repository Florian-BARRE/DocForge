// ====== Code Summary ======
// FailurePolicyControl — "If all providers fail" section in the chain ladder.
// Renders failure_policy (raise | continue) as a calm segmented control with a
// one-line consequence hint. When "continue" is selected, reveals on_degraded.
// Styled neutral/informational — this is a SETTING, not an error alarm.

// ====== Internal Project Imports ======
import type { ConfigNode } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FailurePolicyControlProps {
  /** Gate child node for failure_policy (enum: raise | continue). */
  policyNode: ConfigNode | undefined
  /** Gate child node for on_degraded (enum: empty | best_effort). */
  degradedNode: ConfigNode | undefined
  /** Current failure_policy value from the draft. */
  policy: string
  /** Current on_degraded value from the draft. */
  onDegraded: string
  /** Write accessor for absolute config dot-paths. */
  writeValue: (absPath: string, v: unknown) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Calm, readable control for the "if all providers fail" behavior.
 *
 * Replaces the old red "Exhausted" terminal bar with a neutral segmented
 * control so the user understands this is a configurable setting, not an
 * alarm. A one-line consequence hint explains what the chosen option does.
 * When "Continue" is selected, the on_degraded sub-choice is revealed inline.
 *
 * Args:
 *   policyNode:   ConfigNode for failure_policy (carries the absolute path for writes).
 *   degradedNode: ConfigNode for on_degraded (carries the absolute path).
 *   policy:       Current failure_policy value (raise | continue).
 *   onDegraded:   Current on_degraded value (empty | best_effort).
 *   writeValue:   Write accessor for absolute dot-paths.
 */
export function FailurePolicyControl({
  policyNode, degradedNode, policy, onDegraded, writeValue,
}: FailurePolicyControlProps) {
  const isRaise = policy === 'raise'

  return (
    <div className="chain-section">
      {/* Section header */}
      <div className="chain-section-head">
        <span className="chain-section-title">If all providers fail</span>
        <span className="chain-section-hint">
          What happens when every provider in the chain errors or is exhausted.
        </span>
      </div>

      {/* Segmented control: Stop vs Continue */}
      <div className="failure-policy-control">
        <button
          type="button"
          className={`failure-policy-btn${isRaise ? ' failure-policy-btn-active' : ''}`}
          onClick={() => policyNode && writeValue(policyNode.path, 'raise')}
        >
          Stop &amp; raise an error
        </button>
        <button
          type="button"
          className={`failure-policy-btn${!isRaise ? ' failure-policy-btn-active' : ''}`}
          onClick={() => policyNode && writeValue(policyNode.path, 'continue')}
        >
          Continue with a degraded result
        </button>
      </div>

      {/* One-line consequence — explains the selected choice in plain English */}
      <p className="failure-policy-consequence">
        {isRaise
          ? 'The pipeline stops and the job is marked as failed.'
          : 'The pipeline continues; downstream stages receive a degraded or empty result.'}
      </p>

      {/* Degraded output sub-choice — only shown when "continue" is selected */}
      {!isRaise && degradedNode && (
        <div className="failure-policy-degraded">
          <span className="field-label" style={{ minWidth: 0, maxWidth: 'none', color: 'var(--text-muted)', fontSize: 11 }}>
            Degraded output
          </span>
          <div className="failure-policy-control" style={{ marginTop: 4 }}>
            <button
              type="button"
              className={`failure-policy-btn${onDegraded === 'empty' ? ' failure-policy-btn-active' : ''}`}
              onClick={() => writeValue(degradedNode.path, 'empty')}
            >
              Empty
            </button>
            <button
              type="button"
              className={`failure-policy-btn${onDegraded === 'best_effort' ? ' failure-policy-btn-active' : ''}`}
              onClick={() => writeValue(degradedNode.path, 'best_effort')}
            >
              Best effort
            </button>
          </div>
          <p className="failure-policy-consequence" style={{ marginTop: 4 }}>
            {onDegraded === 'empty'
              ? 'Returns an empty result — downstream stages see no content for this step.'
              : 'Returns whatever the last provider produced, even if partial or low quality.'}
          </p>
        </div>
      )}
    </div>
  )
}
