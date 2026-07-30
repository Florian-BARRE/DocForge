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

/** The vectors on the shelves; `c` marks the three canonical embers kept lit when motion is off. */
const DOTS: { x: number; y: number; c?: boolean }[] = [
  { x: 28, y: 60 }, { x: 42, y: 60 }, { x: 56, y: 60, c: true }, { x: 70, y: 60 },
  { x: 28, y: 76 }, { x: 42, y: 76, c: true }, { x: 56, y: 76 }, { x: 70, y: 76 },
  { x: 28, y: 91, c: true }, { x: 42, y: 91 }, { x: 56, y: 91 }, { x: 70, y: 91 },
];
const CYCLE = 2.8;
// Where the bead lands (top shelf, under the right cup), and when in the cycle it lands. Each dot's
// flare is delayed by its distance to the impact so the heat diffuses outward from that point.
const IMPACT = { x: 56, y: 60 };
const IMPACT_FRAC = 0.6;
const SPREAD = 0.26;
const PEAK = 0.08;
const dist = (d: { x: number; y: number }) => Math.hypot(d.x - IMPACT.x, d.y - IMPACT.y);
const MAX_DIST = Math.max(...DOTS.map(dist));

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

      {/* Pour-lip + LEFT drip cup — the molten metal at rest on the lip (gently glowing). */}
      <g className="forge-el forge-spout">
        <rect x="24" y="33" width="50" height="5" fill={accent} />
        <path d="M34 38 v6 a3.5 3.5 0 0 0 7 0 v-6 Z" fill={accent} />
      </g>

      {/* RIGHT drip cup — elongates, sheds a bead, then reforms to its initial size each loop. */}
      <path d="M52 38 v8 a3.5 3.5 0 0 0 7 0 v-8 Z" fill={accent} className={animated ? "forge-teat" : undefined} />
      {animated && <circle cx="55.5" cy="51" r="2.5" fill={ember} className="forge-el forge-fall" />}

      {/* Three layer shelves — where the melt casts into vectors. */}
      <rect x="16" y="54" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="70" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="86" width="64" height="10" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />

      {/* Vectors — heat diffuses outward from the bead's impact point (see index.css). */}
      {DOTS.map((d, i) => {
        const flareFrac = IMPACT_FRAC + (dist(d) / MAX_DIST) * SPREAD;
        const delay = (flareFrac - PEAK - 1) * CYCLE; // negative → running from load
        return (
          <circle
            key={i}
            cx={d.x}
            cy={d.y}
            r={d.y === 91 ? 2.6 : 2.8}
            fill={!animated && d.c ? accent : steel}
            className={animated ? `forge-dot${d.c ? " c" : ""}` : undefined}
            style={animated ? { animationDelay: `${delay.toFixed(3)}s` } : undefined}
          />
        );
      })}
    </svg>
  );
}
