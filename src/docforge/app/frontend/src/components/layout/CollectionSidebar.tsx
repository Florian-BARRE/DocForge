// ====== Code Summary ======
// Left sidebar that lists all collections with a status dot and document count
// badge. Polls the API every 5 seconds to stay up to date without requiring
// the parent to push down a refresh signal.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { listCollections } from '../../api/client'
import type { Collection } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface CollectionSidebarProps {
  /** ID of the currently selected collection, or null if none is selected. */
  activeCollectionId: string | null
  /** Called when the user clicks a collection row. */
  onSelect: (id: string) => void
  /** Called when the user clicks the "+ New Collection" button. */
  onNew: () => void
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Returns true when the collection has at least one document that finished
 * ingestion successfully, which is used to determine the status dot colour.
 *
 * Args:
 *   collection: The collection object returned by the API.
 *
 * Returns:
 *   True if the collection has processed documents, false otherwise.
 */
function hasProcessedDocs(collection: Collection): boolean {
  // stats may be absent on older API responses — treat undefined as zero.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const count = (collection as any).stats?.doc_count ?? 0
  return count > 0
}

/**
 * Extracts the total document count from the optional stats field.
 *
 * Args:
 *   collection: The collection object returned by the API.
 *
 * Returns:
 *   The document count, or 0 if stats are unavailable.
 */
function docCount(collection: Collection): number {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (collection as any).stats?.doc_count ?? 0
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Fixed-width left sidebar listing all collections.
 *
 * Each row shows a colour-coded status dot (green when the collection has
 * processed documents, grey otherwise), the collection name, and a document
 * count badge. The active collection is highlighted with an accent background
 * and a left border.
 *
 * Collections are fetched on mount and re-fetched every 5 seconds via a
 * lightweight polling loop so the count badges stay current without any
 * external refresh trigger.
 *
 * Args:
 *   activeCollectionId: ID of the collection to highlight, or null.
 *   onSelect:           Callback fired when a row is clicked.
 *   onNew:              Callback fired when the "+ New Collection" button is clicked.
 */
export function CollectionSidebar({ activeCollectionId, onSelect, onNew }: CollectionSidebarProps) {
  const [collections, setCollections] = useState<Collection[]>([])

  // 1. Fetch collections on mount and poll every 5 s.
  useEffect(() => {
    let cancelled = false

    async function fetch() {
      try {
        const res = await listCollections()
        if (!cancelled) setCollections(res.collections)
      } catch {
        // Silently ignore transient network errors between polls.
      }
    }

    void fetch()
    const interval = setInterval(() => { void fetch() }, 5000)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <aside className="sidebar">
      {/* ── Header ── */}
      <div className="sidebar-header">Collections</div>

      {/* ── Collection list ── */}
      <ul className="sidebar-list" role="listbox" aria-label="Collections">
        {collections.map(col => {
          const isActive = col.id === activeCollectionId
          const done = hasProcessedDocs(col)
          const count = docCount(col)

          return (
            <li
              key={col.id}
              role="option"
              aria-selected={isActive}
              className={`sidebar-row${isActive ? ' sidebar-row-active' : ''}`}
              onClick={() => onSelect(col.id)}
            >
              {/* Status dot: green when docs are done, grey otherwise */}
              <span
                className="sidebar-dot"
                style={{ background: done ? 'var(--s-done)' : 'var(--text-dim)' }}
                title={done ? 'Has processed documents' : 'No processed documents'}
              />

              {/* Collection name */}
              <span className="sidebar-name" title={col.name}>{col.name}</span>

              {/* Document count badge */}
              {count > 0 && (
                <span className="sidebar-count">{count}</span>
              )}
            </li>
          )
        })}

        {collections.length === 0 && (
          <li className="sidebar-row" style={{ pointerEvents: 'none', opacity: 0.5 }}>
            <span className="sidebar-name">No collections</span>
          </li>
        )}
      </ul>

      {/* ── Footer: create new collection ── */}
      <div className="sidebar-footer">
        <button
          type="button"
          className="sidebar-new-btn"
          onClick={onNew}
        >
          + New Collection
        </button>
      </div>
    </aside>
  )
}
