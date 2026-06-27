// ====== Code Summary ======
// ProviderCard — a single provider entry in the ChainLadder fallback ladder.
// Shows the provider's role badge (Primary / Fallback N), availability dot,
// name, and an expandable "Settings" section for provider params (rendered via
// the injected renderChildren render-prop). Supports reorder and remove actions.

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
  /** 1-based rank position in the fallback ladder (drives the role label). */
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

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Derive a human-readable role label from a 1-based ladder rank.
 * The first provider is "Primary"; subsequent ones are "Fallback 1", "Fallback 2", etc.
 *
 * Args:
 *   rank: 1-based position in the chain.
 *
 * Returns:
 *   string: Role label for display.
 */
function roleLabel(rank: number): string {
  return rank === 1 ? 'Primary' : `Fallback ${rank - 1}`
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * A single provider card in the ChainLadder fallback ladder.
 *
 * Displays a role badge ("Primary" / "Fallback N") instead of a bare number,
 * along with the availability dot, provider name, and reorder/remove controls.
 * When the provider has configurable params the header toggles an inline
 * "Settings" section rendered via the injected render-prop.
 *
 * Args:
 *   rank:           Position in the fallback ladder (1-based; drives the role label).
 *   entry:          Raw chain entry object { id, ...params }.
 *   choice:         Matching ProviderChoice from discovery (for label + params).
 *   isFirst:        Disables the move-up button when true.
 *   isLast:         Disables the move-down button when true.
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
  const role = roleLabel(rank)

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
        {/* Role badge — "Primary" for rank 1, "Fallback N" for the rest */}
        <span
          className={`provider-role-badge ${rank === 1 ? 'provider-role-primary' : 'provider-role-fallback'}`}
          aria-label={`${role} provider`}
        >
          {role}
        </span>

        {/* Availability status dot */}
        <span
          className={`provider-card-avail-dot ${isAvailable ? 'provider-card-avail-dot-ok' : 'provider-card-avail-dot-missing'}`}
          title={isAvailable ? 'Available in this deployment' : 'Unavailable in this deployment'}
          aria-label={isAvailable ? 'available' : 'unavailable'}
        />

        {/* Provider name */}
        <span className="provider-card-name">{displayName}</span>

        {/* Unavailability hint */}
        {!isAvailable && (
          <span className="provider-card-unavail-hint">unavailable</span>
        )}

        {/* Settings expand/collapse indicator */}
        {hasParams && (
          <span className="provider-card-expand" aria-hidden="true">
            Settings {expanded ? '▲' : '▼'}
          </span>
        )}

        {/* Reorder + remove action buttons */}
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

      {/* Inline settings section — shown when expanded */}
      {expanded && hasParams && (
        <div className="provider-card-params">
          {renderChildren(params, readEntry, writeEntry)}
        </div>
      )}
    </div>
  )
}
