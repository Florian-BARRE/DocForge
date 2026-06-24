// ====== Code Summary ======
// Shared config-draft hook for the configuration panels.
// Replaces the previous per-panel debounced auto-save with an explicit, buffered
// "save / discard" workflow. Field edits accumulate a top-level patch (deep-merged)
// in local state; nothing is sent to the server until save() is invoked. Exposes
// the draft status so panels can surface an "unsaved changes" indicator and gate
// their Save / Discard buttons.

// ====== Third-Party Library Imports ======
import { useCallback, useState } from 'react'

// ====== Internal Project Imports ======
import { updateConfig } from '../api/client'
import type { ConfigApplied } from '../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Lifecycle status of an in-progress config draft. */
export type DraftStatus = 'clean' | 'dirty' | 'saving' | 'saved' | 'error'

/** Public surface returned by {@link useConfigDraft}. */
export interface ConfigDraft {
  /** Accumulate a top-level patch into the pending buffer (deep-merged). */
  stage: (patch: Record<string, unknown>) => void
  /** Persist the accumulated patch with a single updateConfig call. */
  save: () => Promise<void>
  /** Drop the buffer and return to a clean state. */
  discard: () => void
  /** Current draft lifecycle status. */
  status: DraftStatus
  /** Whether there are unsaved changes in the buffer. */
  isDirty: boolean
  /** The accumulated patch awaiting persistence. */
  pending: Record<string, unknown>
  /**
   * Transparency envelope returned by the last successful save (what the
   * backend actually applied), or null when no save has completed yet.
   */
  applied: ConfigApplied | null
}

/** Milliseconds the "saved" confirmation stays visible before reverting to clean. */
const SAVED_FLASH_MS = 2000

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Determine whether a value is a plain mergeable object (not null, not an array).
 *
 * Args:
 *   v: Value to inspect.
 *
 * Returns:
 *   boolean: True when v is a non-null, non-array object.
 */
function isPlainObject(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

/**
 * Recursively deep-merge two patch objects.
 *
 * For each key: when both sides hold plain objects they are merged recursively;
 * otherwise the value from `b` overwrites the value from `a`. Lists and scalars
 * always overwrite — they are never merged element-wise.
 *
 * Args:
 *   a: Base object (the existing pending buffer).
 *   b: Incoming patch to layer on top of `a`.
 *
 * Returns:
 *   Record<string, unknown>: A new merged object (inputs are not mutated).
 */
function deepMerge(
  a: Record<string, unknown>,
  b: Record<string, unknown>,
): Record<string, unknown> {
  // 1. Start from a shallow copy of the base so inputs stay immutable.
  const out: Record<string, unknown> = { ...a }

  // 2. Layer every key from the incoming patch.
  for (const [key, bVal] of Object.entries(b)) {
    const aVal = out[key]
    if (isPlainObject(aVal) && isPlainObject(bVal)) {
      // Both sides are objects → merge recursively.
      out[key] = deepMerge(aVal, bVal)
    } else {
      // Lists and scalars overwrite outright.
      out[key] = bVal
    }
  }

  return out
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Manage a buffered configuration draft for a single panel.
 *
 * Edits are accumulated locally via {@link ConfigDraft.stage} and only flushed to
 * the backend when {@link ConfigDraft.save} is called. The hook never schedules
 * implicit saves — persistence is fully explicit.
 *
 * Args:
 *   collectionId: Target collection for config persistence.
 *   onSaved:      Optional callback fired after a successful save.
 *
 * Returns:
 *   ConfigDraft: The draft control surface (stage / save / discard + status).
 */
export function useConfigDraft(collectionId: string, onSaved?: () => void): ConfigDraft {
  const [pending, setPending] = useState<Record<string, unknown>>({})
  const [isDirty, setIsDirty] = useState(false)
  const [status, setStatus] = useState<DraftStatus>('clean')
  const [applied, setApplied] = useState<ConfigApplied | null>(null)

  // 1. Accumulate a top-level patch into the pending buffer (deep-merged).
  const stage = useCallback((patch: Record<string, unknown>) => {
    setPending(prev => deepMerge(prev, patch))
    setIsDirty(true)
    setStatus('dirty')
  }, [])

  // 2. Persist the accumulated patch with a single updateConfig call.
  const save = useCallback(async () => {
    if (!isDirty) return
    // Reset any previous transparency envelope before a fresh save.
    setApplied(null)
    setStatus('saving')
    try {
      const response = await updateConfig(collectionId, pending, 'Updated config')
      setApplied(response.applied ?? null)
      setPending({})
      setIsDirty(false)
      setStatus('saved')
      onSaved?.()
      // Flash the "saved" confirmation, then settle back to neutral.
      setTimeout(() => setStatus('clean'), SAVED_FLASH_MS)
    } catch {
      setStatus('error')
    }
  }, [collectionId, isDirty, pending, onSaved])

  // 3. Drop the buffer and return to a clean state.
  //    Local field re-seeding is handled by each panel via its reset nonce.
  const discard = useCallback(() => {
    setPending({})
    setIsDirty(false)
    setStatus('clean')
    setApplied(null)
  }, [])

  return { stage, save, discard, status, isDirty, pending, applied }
}
