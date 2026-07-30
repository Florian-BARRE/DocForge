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
  /** Run the molten-drip loop. Off renders the mark at rest (used for icons/favicons). */
  animated?: boolean;
  title?: string;
}

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

      {/* The falling bead of lava. */}
      <circle cx="47" cy="49" r="2.6" fill={ember} className="forge-el forge-drip" />

      {/* Three layer shelves — where the melt casts into vectors. */}
      <rect x="16" y="54" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="70" width="64" height="12" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />
      <rect x="16" y="86" width="64" height="10" rx="3" fill={paper} stroke={ink} strokeWidth={3.5} />

      {/* Vectors at rest. */}
      <g fill={steel}>
        <circle cx="28" cy="60" r="2.8" /><circle cx="42" cy="60" r="2.8" /><circle cx="70" cy="60" r="2.8" />
        <circle cx="28" cy="76" r="2.8" /><circle cx="56" cy="76" r="2.8" /><circle cx="70" cy="76" r="2.8" />
        <circle cx="42" cy="91" r="2.6" /><circle cx="56" cy="91" r="2.6" /><circle cx="70" cy="91" r="2.6" />
      </g>

      {/* The struck vectors — one per shelf, flaring in a top→down cascade. */}
      <circle cx="56" cy="60" r="2.8" fill={accent} className="forge-el forge-strike" />
      <circle cx="42" cy="76" r="2.8" fill={accent} className="forge-el forge-strike s2" />
      <circle cx="28" cy="91" r="2.6" fill={accent} className="forge-el forge-strike s3" />
    </svg>
  );
}
