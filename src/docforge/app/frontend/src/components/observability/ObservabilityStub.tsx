// ====== Code Summary ======
// ObservabilityStub — placeholder for the Observability zone (not yet built).
// Renders a centered "coming soon" message in the cockpit shell.
// Will be replaced by the full Observability implementation in a later chunk.

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Coming-soon placeholder for the Observability zone.
 *
 * Rendered by AppShell when the user navigates to the Observability entry
 * in the nav rail. Interior will be replaced in a later UI chunk.
 */
export function ObservabilityStub() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      gap: 12,
      color: 'var(--text-dim)',
    }}>
      <span style={{ fontSize: 32, opacity: 0.3 }}>📊</span>
      <span style={{ fontSize: 14, color: 'var(--text-muted)' }}>Observability</span>
      <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Coming in a future release</span>
    </div>
  )
}
