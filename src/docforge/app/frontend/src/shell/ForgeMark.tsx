// ====== Code Summary ======
// The DocForge mark, rendered inline and animated: molten lava beads off the document's pour-lip,
// falls onto the layer shelves below, and each orange "vector" strikes alight in a top→down
// cascade — the whole "INGESTION, FORGED" idea in one loop. Colours come from theme tokens (never
// hardcoded), so it reskins in light/dark; the motion classes live in index.css and honour
// prefers-reduced-motion.

import { theme as t } from "../theme";

interface ForgeMarkProps {
  /** Rendered edge length in px (the art is a 96×96 square). */
  size?: number;
  /** Run the molten-casting loop. Off renders the mark at rest (used for icons/favicons). */
  animated?: boolean;
  title?: string;
}

/** Vectors in a snake path (→ ← →) so the travelling spark sweeps continuously; `c` marks the
 *  three canonical embers kept lit when motion is off. */
const DOTS: { x: number; y: number; c?: boolean }[] = [
  { x: 28, y: 60 }, { x: 42, y: 60 }, { x: 56, y: 60, c: true }, { x: 70, y: 60 },
  { x: 70, y: 76 }, { x: 56, y: 76 }, { x: 42, y: 76, c: true }, { x: 28, y: 76 },
  { x: 28, y: 91, c: true }, { x: 42, y: 91 }, { x: 56, y: 91 }, { x: 70, y: 91 },
];
const CYCLE = 2.8;

export function ForgeMark({ size = 30, animated = true, title = "DocForge" }: ForgeMarkProps) {
  const paper = t.color.panel;
  const ink = t.color.text;
  const steel = t.color.mute;
  const accent = t.color.accent;
  const ember = t.color.warn;
  return (
    <svg
      viewBox="-2 -1 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={title}
      className={animated ? "forge-anim" : undefined}
      style={{ display: "block", flexShrink: 0 }}
    >
      <title>{title}</title>

      {/* Document — paper body with a folded corner + two ruled lines. */}
      <path d="M24 2 H60 L74 16 V38 H24 Z" fill={paper} stroke={ink} strokeWidth={4} strokeLinejoin="round" />
      <path d="M60 2 V16 H74" fill="none" stroke={ink} strokeWidth={4} strokeLinejoin="round" />
      <rect x="31" y="11" width="24" height="3.6" rx="1.8" fill={steel} />
      <rect x="31" y="19" width="30" height="3.6" rx="1.8" fill={steel} />

      {/* Pour-lip + drip cups — the molten metal running off the document. */}
      <g className="forge-el forge-spout">
        <rect x="24" y="33" width="50" height="5" fill={accent} />
        <path d="M34 38 v6 a3.5 3.5 0 0 0 7 0 v-6 Z M52 38 v8 a3.5 3.5 0 0 0 7 0 v-8 Z" fill={accent} />
      </g>

      {/* The molten strand pouring from the lip, and the bead that pinches off it. */}
      <rect x="45.4" y="44" width="3.2" height="9" rx="1.6" fill={accent} className={animated ? "forge-pour" : undefined} />
      {animated && <circle cx="47" cy="52" r="2.5" fill={ember} className="forge-el forge-bead" />}

      {/* Three layer shelves — where the melt casts into vectors. */}
      <rect x="16" y="54" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="70" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="86" width="64" height="10" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />

      {/* Vectors — a single spark of heat travels along them (see index.css). */}
      {DOTS.map((d, i) => (
        <circle
          key={i}
          cx={d.x}
          cy={d.y}
          r={d.y === 91 ? 2.6 : 2.8}
          fill={!animated && d.c ? accent : steel}
          className={animated ? `forge-dot${d.c ? " c" : ""}` : undefined}
          style={animated ? { animationDelay: `${(-(i / DOTS.length) * CYCLE).toFixed(3)}s` } : undefined}
        />
      ))}
    </svg>
  );
}
