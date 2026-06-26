// ====== Code Summary ======
// StageConnector — SVG arrowhead connector rendered between stage flow nodes.
// Pure presentational component; color comes from CSS custom properties only.

// ── Component ─────────────────────────────────────────────────────────────────

interface StageConnectorProps {
  /** When true, the connector is tinted with the accent color to show flow. */
  highlighted?: boolean
}

/**
 * Horizontal SVG arrowhead connector placed between two stage flow node cards.
 *
 * Renders a short line ending in a solid triangle arrowhead. The color is
 * driven entirely by CSS custom properties so it adapts to both themes.
 *
 * Args:
 *   highlighted: Optional tint with the accent color when the destination
 *     stage is active.
 */
export function StageConnector({ highlighted = false }: StageConnectorProps) {
  return (
    <div
      className={`stage-connector${highlighted ? ' stage-connector-hl' : ''}`}
      aria-hidden="true"
    >
      {/* 44 × 24 viewport — line from left edge to tip, then arrowhead polygon */}
      <svg
        width="44"
        height="24"
        viewBox="0 0 44 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Horizontal stem */}
        <line
          x1="0"
          y1="12"
          x2="35"
          y2="12"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        {/* Arrowhead triangle */}
        <polygon
          points="34,7 44,12 34,17"
          fill="currentColor"
        />
      </svg>
    </div>
  )
}
