// ====== Code Summary ======
// HighlightedText — splits text on query terms (>2 chars) and wraps the matches in
// <mark> elements for in-result term highlighting. Extracted from ResultCard.

// ====== Third-Party Library Imports ======
import { useMemo } from 'react'

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Splits text on query terms (>2 chars) and wraps matches in <mark> elements.
 *
 * Uses a capture-group regex split so matched terms land at odd-numbered indices,
 * allowing them to be wrapped without an extra pass.
 *
 * Args:
 *   text:  The raw text to highlight.
 *   query: The search query string — terms shorter than 3 chars are skipped.
 */
export function HighlightedText({ text, query }: { text: string; query: string }) {
  const terms = useMemo(
    () => query.trim().split(/\s+/).filter(t => t.length > 2),
    [query],
  )
  if (terms.length === 0) return <>{text}</>

  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)

  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1
          ? <mark key={i} className="search-highlight">{part}</mark>
          : part,
      )}
    </>
  )
}
