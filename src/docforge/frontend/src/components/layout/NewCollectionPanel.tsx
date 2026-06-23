// ====== Code Summary ======
// Form panel for creating a new collection. Accepts a name, calls createCollection,
// then fires onCreated with the new collection's ID so the parent can navigate to it.

// ====== Third-Party Library Imports ======
import { useState } from 'react'
import type { FormEvent } from 'react'

// ====== Internal Project Imports ======
import { createCollection } from '../../api/client'

// ── Types ────────────────────────────────────────────────────────────────────

interface NewCollectionPanelProps {
  /** Called with the new collection ID after successful creation. */
  onCreated: (collectionId: string) => void
  /** Called when the user cancels without creating. */
  onCancel: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Minimal collection creation form.
 *
 * The user enters a name and clicks "Create". The collection is created with
 * backend defaults; all pipeline stages can then be configured via the Pipeline
 * tab's discovery-driven graph.
 *
 * Args:
 *   onCreated: Callback fired with the new collection's ID after a successful POST.
 *   onCancel:  Callback fired when the user dismisses the panel without creating.
 */
export function NewCollectionPanel({ onCreated, onCancel }: NewCollectionPanelProps) {
  const [name, setName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /**
   * Submits the creation form.
   *
   * Args:
   *   e: The form submit event (preventDefault called to avoid page reload).
   */
  async function handleSubmit(e: FormEvent) {
    // 1. Prevent default HTML form submission.
    e.preventDefault()

    const trimmed = name.trim()
    if (!trimmed) return

    // 2. Call the API and forward the new collection ID to the parent.
    setIsLoading(true)
    setError(null)
    try {
      const collection = await createCollection({ name: trimmed })
      onCreated(collection.id)
    } catch (err) {
      setError(String(err))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="new-collection-panel">
      <div className="new-collection-title">New Collection</div>

      <p className="new-collection-hint">
        Give your collection a name. You can configure all pipeline stages from
        the Pipeline tab once the collection is created.
      </p>

      <form onSubmit={handleSubmit}>
        <div className="new-collection-field">
          <label htmlFor="col-name" className="new-collection-label">Name</label>
          <input
            id="col-name"
            type="text"
            className="input"
            placeholder="e.g. research-papers"
            value={name}
            onChange={e => setName(e.target.value)}
            disabled={isLoading}
            autoFocus
          />
        </div>

        {error && (
          <div className="error-banner" style={{ marginTop: 8 }}>{error}</div>
        )}

        <div className="new-collection-actions">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onCancel}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={isLoading || !name.trim()}
          >
            {isLoading ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  )
}
