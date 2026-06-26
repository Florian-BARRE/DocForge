// ====== Code Summary ======
// KeyRevealCallout — one-time display of the plaintext API key after creation.
// The key is shown exactly once; after the user dismisses, it is gone forever.
// Provides a copy-to-clipboard button and a clear "you won't see this again" warning.

import { useState } from 'react'
import type { ApiKeyCreatedResponse } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface KeyRevealCalloutProps {
  /** The creation response containing the plaintext key. */
  created: ApiKeyCreatedResponse
  /** Called when the user dismisses the callout. */
  onDismiss: () => void
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Full-width callout that displays a newly created API key exactly once.
 *
 * Sections:
 *   1. Warning header — name + "copy now" instruction.
 *   2. Monospace key value + copy button.
 *   3. Dismiss button — removes the callout (key is gone from the response object).
 *
 * Args:
 *   created:   The ApiKeyCreatedResponse from POST /auth/keys.
 *   onDismiss: Callback to clear the callout from the parent's state.
 */
export function KeyRevealCallout({ created, onDismiss }: KeyRevealCalloutProps) {
  const [copied, setCopied] = useState(false)

  /**
   * Copies the plaintext key to the clipboard.
   */
  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(created.key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      // Clipboard API unavailable (non-HTTPS / denied) — user can select manually.
    }
  }

  return (
    <div style={{
      background: 'color-mix(in srgb, var(--s-done) 8%, var(--surface))',
      border: '1px solid color-mix(in srgb, var(--s-done) 30%, transparent)',
      borderRadius: 'var(--radius)',
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      {/* ── Header ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--s-done)' }}>
          Key created: {created.name}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          Copy the key now — you will NOT be able to see the plaintext again after dismissing.
        </span>
      </div>

      {/* ── Key value + copy ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <code style={{
          flex: 1,
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          padding: '6px 10px',
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text)',
          wordBreak: 'break-all',
          userSelect: 'all',
        }}>
          {created.key}
        </code>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => { void handleCopy() }}
          style={{ flexShrink: 0, padding: '5px 12px' }}
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>

      {/* ── Dismiss ── */}
      <button
        type="button"
        className="btn"
        onClick={onDismiss}
        style={{ alignSelf: 'flex-start', fontSize: 11 }}
      >
        I have saved it — dismiss
      </button>
    </div>
  )
}
