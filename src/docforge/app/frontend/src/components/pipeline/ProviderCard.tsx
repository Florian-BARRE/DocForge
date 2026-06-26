// ====== Code Summary ======
// ProviderCard — a single provider entry in the ChainLadder fallback ladder.
// Shows the provider's rank badge, availability dot, name, and optional param
// section (rendered via the injected renderChildren render-prop). Supports
// remove, move-up, and move-down actions for ladder reordering.

// ====== Third-Party Library Imports ======
import { useState } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode, ProviderChoice } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Render-prop type matching RecursiveFieldRenderer's signature. */
export type RenderChildrenFn = (
  nodes: ConfigNode[],
  readValue: (absPath: string) => unknown,
  writeValue: (absPath: string, v: unknown) => void,
) => ReactNode

interface ProviderCardProps {
  /** 1-based rank position in the fallback ladder. */
  rank: number
  /** Raw chain entry from the config value array. */
  entry: { id: string; [k: string]: unknown }
  /** Matching ProviderChoice from the chain node's choices list (may be undefined). */
  choice: ProviderChoice | undefined
  /** Whether this is the first item in the ladder (disables move-up). */
  isFirst: boolean
  /** Whether this is the last item in the ladder (disables move-down). */
  isLast: boolean
  /** Move this provider one position up. */
  onMoveUp: () => void
  /** Move this provider one position down. */
  onMoveDown: () => void
  /** Remove this provider from the ladder. */
  onRemove: () => void
  /** Injected recursive renderer for provider params. */
  renderChildren: RenderChildrenFn
  /** Read a param value for this chain entry using the param's absolute path. */
  readEntry: (absPath: string) => unknown
  /** Write a param value for this chain entry using the param's absolute path. */
  writeEntry: (absPath: string, v: unknown) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * A single provider card in the ChainLadder fallback ladder.
 *
 * Displays the rank badge, availability status dot, provider label, and action
 * buttons (up / down / remove). When the provider has configurable params the
 * header toggles an inline params section rendered via the injected render-prop.
 *
 * Args:
 *   rank:           Position in the fallback ladder (1-based).
 *   entry:          Raw chain entry object { id, ...params }.
 *   choice:         Matching ProviderChoice from discovery (for label + params).
 *   isFirst:        Disables the move-up button.
 *   isLast:         Disables the move-down button.
 *   onMoveUp:       Callback to shift the provider one position up.
 *   onMoveDown:     Callback to shift the provider one position down.
 *   onRemove:       Callback to remove the provider from the ladder.
 *   renderChildren: Injected renderer for provider sub-params.
 *   readEntry:      Read accessor for this entry's flat param values.
 *   writeEntry:     Write accessor for this entry's flat param values.
 */
export function ProviderCard({
  rank, entry, choice, isFirst, isLast,
  onMoveUp, onMoveDown, onRemove,
  renderChildren, readEntry, writeEntry,
}: ProviderCardProps) {
  const [expanded, setExpanded] = useState(false)
  const params = choice?.params ?? []
  const hasParams = params.length > 0
  const displayName = choice?.label || entry.id
  const isAvailable = choice?.available ?? true

  return (
    <div className="provider-card">
      {/* Header row */}
      <div
        className="provider-card-head"
        onClick={() => { if (hasParams) setExpanded(e => !e) }}
        role={hasParams ? 'button' : undefined}
        tabIndex={hasParams ? 0 : undefined}
        onKeyDown={e => { if (hasParams && (e.key === 'Enter' || e.key === ' ')) setExpanded(v => !v) }}
        aria-expanded={hasParams ? expanded : undefined}
      >
        {/* Rank badge */}
        <span className="provider-card-rank" aria-label={`Provider ${rank}`}>{rank}</span>

        {/* Availability dot */}
        <span
          className={`provider-card-avail-dot ${isAvailable ? 'provider-card-avail-dot-ok' : 'provider-card-avail-dot-missing'}`}
          title={isAvailable ? 'Available' : 'Unavailable in this deployment'}
          aria-label={isAvailable ? 'available' : 'unavailable'}
        />

        {/* Provider name */}
        <span className="provider-card-name">{displayName}</span>

        {/* Availability hint for missing providers */}
        {!isAvailable && (
          <span className="provider-card-unavail-hint">unavailable</span>
        )}

        {/* Params expand/collapse indicator */}
        {hasParams && (
          <span className="provider-card-expand" aria-hidden="true">
            {expanded ? '▲' : '▼'}
          </span>
        )}

        {/* Action buttons */}
        <div
          className="provider-card-actions"
          onClick={e => e.stopPropagation()}
        >
          <button
            type="button"
            className="btn-icon"
            onClick={onMoveUp}
            disabled={isFirst}
            aria-label="Move up"
            title="Move up"
          >↑</button>
          <button
            type="button"
            className="btn-icon"
            onClick={onMoveDown}
            disabled={isLast}
            aria-label="Move down"
            title="Move down"
          >↓</button>
          <button
            type="button"
            className="btn-icon btn-icon-danger"
            onClick={onRemove}
            aria-label={`Remove ${displayName}`}
            title="Remove"
          >✕</button>
        </div>
      </div>

      {/* Inline params section — shown when expanded */}
      {expanded && hasParams && (
        <div className="provider-card-params">
          {renderChildren(params, readEntry, writeEntry)}
        </div>
      )}
    </div>
  )
}
