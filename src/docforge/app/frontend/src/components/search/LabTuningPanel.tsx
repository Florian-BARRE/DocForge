// ====== Code Summary ======
// LabTuningPanel — collapsible "Tuning" section of the Search Lab.
// Shows per-query override controls (vector mode, fusion, transform, rerank,
// weights) next to the query bar.  Each control displays the saved-config
// baseline and marks itself as "overriding" when the user changes it.
// A "Reset to config" button clears all overrides at once.

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Local Project Imports ======
import type { SearchBaseline, SearchOverrides } from './labTypes'
import { SegmentedControl } from './SegmentedControl'
import { Toggle } from '../ui/primitives/Toggle'

// ── Constants ─────────────────────────────────────────────────────────────────

const VECTOR_MODE_OPTIONS: { value: SearchBaseline['vector_mode']; label: string }[] = [
  { value: 'dense',  label: 'Dense'  },
  { value: 'sparse', label: 'Sparse' },
  { value: 'hybrid', label: 'Hybrid' },
]

const FUSION_OPTIONS: { value: SearchBaseline['fusion']; label: string }[] = [
  { value: 'rrf',  label: 'RRF'  },
  { value: 'dbsf', label: 'DBSF' },
]

const TRANSFORM_OPTIONS: { value: SearchBaseline['query_transform_strategy']; label: string }[] = [
  { value: 'none',        label: 'None'        },
  { value: 'rewrite',     label: 'Rewrite'     },
  { value: 'hyde',        label: 'HyDE'        },
  { value: 'multi_query', label: 'Multi-query' },
]

// ── Types ─────────────────────────────────────────────────────────────────────

interface LabTuningPanelProps {
  /** Saved config baseline — shown as annotation per control. */
  baseline: SearchBaseline
  /** Current displayed values (baseline + any user overrides). */
  display: SearchBaseline
  /** Non-empty keys = which fields are currently overriding the config. */
  overrides: SearchOverrides
  /** True when at least one control is overriding the baseline. */
  isOverriding: boolean
  /** Named vectors available for weight editing. */
  vectorNames: string[]
  /** Current weight overrides (empty = use backend defaults). */
  localWeights: Record<string, number>
  /** 422 or config-incompatibility error to show inline. */
  errorMessage: string | null
  /** Called when any single field value changes. */
  onUpdate: <K extends keyof SearchBaseline>(key: K, value: SearchBaseline[K]) => void
  /** Called when weight map changes. */
  onUpdateWeights: (weights: Record<string, number>) => void
  /** Called when the user clicks "Reset to config". */
  onReset: () => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Small orange dot rendered next to a control label when it is overriding the
 * saved config.
 */
function OverrideDot() {
  return <span className="lab-override-dot" title="Overriding saved config" />
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Collapsible tuning panel for the Search Lab.
 *
 * Closed by default; a toggle row shows an override summary when collapsed.
 * When open, renders four control rows (vector mode, fusion, transform, rerank)
 * and an optional weights section for known named vectors.
 *
 * Args:
 *   baseline:       Saved config values (shown as annotations).
 *   display:        What the controls render (baseline + user overrides).
 *   overrides:      Which fields currently differ from baseline.
 *   isOverriding:   Whether any override is active (gates Reset button).
 *   vectorNames:    Named vectors to show weight inputs for.
 *   localWeights:   Current user-set weight overrides.
 *   errorMessage:   Inline error (422 / config incompatibility).
 *   onUpdate:       Field change callback.
 *   onUpdateWeights:Weight change callback.
 *   onReset:        Clear-all-overrides callback.
 */
export function LabTuningPanel({
  baseline,
  display,
  overrides,
  isOverriding,
  vectorNames,
  localWeights,
  errorMessage,
  onUpdate,
  onUpdateWeights,
  onReset,
}: LabTuningPanelProps) {
  const [open, setOpen] = useState(false)

  // 1. Derive a compact override summary for the collapsed state.
  const overrideSummary = Object.keys(overrides).length > 0
    ? `${Object.keys(overrides).length} override${Object.keys(overrides).length > 1 ? 's' : ''}`
    : null

  return (
    <div className="lab-tuning-panel">
      {/* ── Toggle header ── */}
      <button
        type="button"
        className="lab-tuning-toggle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="metadata-form-chevron">{open ? '▾' : '▸'}</span>
        <span style={{ fontWeight: 500 }}>Tuning</span>
        {!open && overrideSummary && (
          <span className="tag tag-running" style={{ fontSize: 10 }}>{overrideSummary}</span>
        )}
        {!open && <span style={{ fontSize: 10, marginLeft: 'auto', opacity: 0.5 }}>Lab overrides</span>}
        {open && isOverriding && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 10, padding: '2px 8px', marginLeft: 'auto' }}
            onClick={e => { e.stopPropagation(); onReset() }}
          >
            Reset to config
          </button>
        )}
      </button>

      {/* ── Body ── */}
      {open && (
        <div className="lab-tuning-body">
          {/* Vector mode */}
          <div className="lab-control-row">
            <span className="lab-control-label">
              Vector mode
              {'vector_mode' in overrides && <OverrideDot />}
            </span>
            <SegmentedControl
              options={VECTOR_MODE_OPTIONS}
              value={display.vector_mode}
              onChange={v => onUpdate('vector_mode', v)}
            />
            <span className="text-dim" style={{ fontSize: 10 }}>
              config: {baseline.vector_mode}
            </span>
          </div>

          {/* Fusion */}
          <div className="lab-control-row">
            <span className="lab-control-label">
              Fusion
              {'fusion' in overrides && <OverrideDot />}
            </span>
            <SegmentedControl
              options={FUSION_OPTIONS}
              value={display.fusion}
              onChange={v => onUpdate('fusion', v)}
            />
            <span className="text-dim" style={{ fontSize: 10 }}>
              config: {baseline.fusion}
            </span>
          </div>

          {/* Query transform */}
          <div className="lab-control-row">
            <span className="lab-control-label">
              Query transform
              {'query_transform_strategy' in overrides && <OverrideDot />}
            </span>
            <select
              className="input select"
              style={{ width: 'auto', fontSize: 11 }}
              value={display.query_transform_strategy}
              onChange={e => onUpdate('query_transform_strategy', e.target.value as SearchBaseline['query_transform_strategy'])}
            >
              {TRANSFORM_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className="text-dim" style={{ fontSize: 10 }}>
              config: {baseline.query_transform_strategy}
            </span>
          </div>

          {/* Rerank toggle */}
          <div className="lab-control-row">
            <span className="lab-control-label">
              Rerank
              {'rerank_enabled' in overrides && <OverrideDot />}
            </span>
            <Toggle
              checked={display.rerank_enabled}
              onChange={v => onUpdate('rerank_enabled', v)}
            />
            <span className="text-dim" style={{ fontSize: 10 }}>
              config: {baseline.rerank_enabled ? 'on' : 'off'}
            </span>
          </div>

          {/* Weights — only when named vectors are known */}
          {vectorNames.length > 0 && (
            <div className="lab-control-row" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
              <span className="lab-control-label">
                Weights
                {Object.keys(localWeights).length > 0 && <OverrideDot />}
              </span>
              {vectorNames.map(name => (
                <div key={name} className="weight-row">
                  <span className="weight-id">{name}</span>
                  <input
                    type="range"
                    className="weight-slider"
                    min={0} max={1} step={0.05}
                    value={localWeights[name] ?? 0.5}
                    onChange={e => {
                      const updated = { ...localWeights, [name]: Number(e.target.value) }
                      onUpdateWeights(updated)
                    }}
                  />
                  <span className="weight-val">{(localWeights[name] ?? 0.5).toFixed(2)}</span>
                </div>
              ))}
            </div>
          )}

          {/* 422 / config error inline */}
          {errorMessage && (
            <div className="lab-422-banner">
              <span style={{ flexShrink: 0 }}>!</span>
              <span>{errorMessage}</span>
            </div>
          )}
        </div>
      )}

      {/* 422 error also shown when panel is collapsed */}
      {!open && errorMessage && (
        <div className="lab-422-banner lab-422-banner-collapsed">
          <span style={{ flexShrink: 0 }}>!</span>
          <span>{errorMessage}</span>
        </div>
      )}
    </div>
  )
}
