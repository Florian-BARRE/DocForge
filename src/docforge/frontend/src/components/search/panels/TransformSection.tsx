// ====== Code Summary ======
// TransformSection — configuration form for the query transform stage of the
// search pipeline. Controls the transform strategy and the number of query
// variants (multi_query only), both stored under pipeline.search.query_transform.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState } from '../../../api/types'

// ====== Local Project Imports ======
import type { TransformStrategy } from './searchConfigHelpers'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface TransformSectionProps {
  configState: ConfigState | null
  searchCfg: Record<string, unknown>
  onSave: (patch: Record<string, unknown>) => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Return a human-readable description for each transform strategy.
 *
 * Args:
 *   strategy: Active transform strategy identifier.
 *
 * Returns:
 *   string: Short description shown below the strategy selector.
 */
function strategyDescription(strategy: TransformStrategy): string {
  switch (strategy) {
    case 'none':        return 'Direct embedding — no query transformation.'
    case 'rewrite':     return 'LLM rewrites the query for better recall.'
    case 'hyde':        return 'Generates a hypothetical passage, then retrieves similar documents.'
    case 'multi_query': return 'Generates N query variants and fuses results with RRF.'
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Configuration form for the query transform stage.
 *
 * Controls the transform strategy (none / rewrite / hyde / multi_query) and the
 * number of query variants for the multi_query strategy. Both values live under
 * `pipeline.search.query_transform`. The LLM provider config is an advanced
 * provider object and is intentionally not editable here.
 *
 * Args:
 *   searchCfg: Extracted pipeline.search object.
 *   onSave:    Callback that receives the pipeline.search patch to persist.
 */
export function TransformSection({ searchCfg, onSave }: TransformSectionProps) {
  const qtCfg = (searchCfg.query_transform as Record<string, unknown>) ?? {}

  // Strategy and n_variants both live under pipeline.search.query_transform.
  const [strategy, setStrategy] = useState<TransformStrategy>(
    (qtCfg.strategy as TransformStrategy | undefined) ?? 'none',
  )
  const [nVariants, setNVariants] = useState<number>(
    (qtCfg.n_variants as number | undefined) ?? 3,
  )

  // Re-seed when configState changes (e.g. parent refreshes after save).
  useEffect(() => {
    const qt = (searchCfg.query_transform as Record<string, unknown>) ?? {}
    setStrategy((qt.strategy as TransformStrategy | undefined) ?? 'none')
    setNVariants((qt.n_variants as number | undefined) ?? 3)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCfg])

  /**
   * Build the query_transform patch and hand it to the parent for persistence.
   *
   * Args:
   *   newStrategy:  Updated strategy value (may be the current one).
   *   newNVariants: Updated n_variants integer.
   */
  function buildAndSave(newStrategy: TransformStrategy, newNVariants: number) {
    onSave({
      query_transform: {
        strategy: newStrategy,
        n_variants: newNVariants,
      },
    })
  }

  function handleStrategyChange(s: TransformStrategy) {
    setStrategy(s)
    buildAndSave(s, nVariants)
  }

  function handleNVariantsChange(v: number) {
    setNVariants(v)
    buildAndSave(strategy, v)
  }

  return (
    <div>
      {/* Strategy selector */}
      <div className="stage-panel-row" style={{ marginBottom: 10 }}>
        <label className="stage-panel-label">Strategy</label>
        <select
          className="input"
          value={strategy}
          onChange={e => handleStrategyChange(e.target.value as TransformStrategy)}
          style={{ flex: 1 }}
        >
          <option value="none">none</option>
          <option value="rewrite">rewrite</option>
          <option value="hyde">hyde</option>
          <option value="multi_query">multi_query</option>
        </select>
      </div>

      {/* Strategy description */}
      <div className="search-stage-description">
        {strategyDescription(strategy)}
      </div>

      {/* n_variants — visible only for multi_query */}
      {strategy === 'multi_query' && (
        <div className="stage-panel-row" style={{ marginBottom: 10 }}>
          <label className="stage-panel-label">Variants</label>
          <input
            className="input"
            type="number"
            min={1}
            max={10}
            value={nVariants}
            onChange={e => handleNVariantsChange(Number(e.target.value))}
            style={{ width: 80 }}
          />
        </div>
      )}
    </div>
  )
}
