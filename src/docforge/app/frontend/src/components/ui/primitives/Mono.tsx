// ====== Code Summary ======
// Mono / Code primitive — renders text in the monospace font stack.
// Used for IDs, hashes, traces, code snippets. Maps to .mono CSS class.

import { HTMLAttributes, ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface MonoProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode
  /** Font size override in px. Defaults to inherited size. */
  size?: number
  /** Color override. Defaults to var(--text-muted). */
  color?: string
  /** If true, renders as a <pre> block with pre-wrap whitespace. */
  block?: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Monospace text span (or block).
 *
 * Uses `.mono` CSS class from global.css (font-mono var, token-driven).
 * Inline by default; pass `block` to render as a scrollable pre block.
 *
 * Args:
 *   size: Font size override in px.
 *   color: Text color override (CSS var or literal).
 *   block: If true renders a pre block with word-break and overflow.
 */
export function Mono({ children, size, color = 'var(--text-muted)', block = false, className = '', style, ...rest }: MonoProps) {
  if (block) {
    return (
      <pre
        className={`mono ${className}`.trim()}
        style={{
          fontSize: size,
          color,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          margin: 0,
          ...style,
        }}
        {...(rest as HTMLAttributes<HTMLPreElement>)}
      >
        {children}
      </pre>
    )
  }

  return (
    <span
      className={`mono ${className}`.trim()}
      style={{ fontSize: size, color, ...style }}
      {...rest}
    >
      {children}
    </span>
  )
}
