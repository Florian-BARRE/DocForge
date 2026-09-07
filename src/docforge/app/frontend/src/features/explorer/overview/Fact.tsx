// ====== Code Summary ======
// Shared label/value cell for the document overview's fact panels — a small uppercase caption over
// a value, with an optional JetBrains Mono rendering (machine values) and a truncated hint tooltip
// for long hashes. Used by both DownloadsPanel and SystemMetadataPanel.

import { theme } from "../../../theme";

/** Shortens a long machine value (a hash) to "lead…trail" — the full value stays available via the
 *  `title` tooltip. A no-op below the threshold, so short mono values (mime types, versions) render
 *  untouched. */
export function truncateHash(value: string, edge = 10): string {
  return value.length <= edge * 2 + 1 ? value : `${value.slice(0, edge)}…${value.slice(-edge)}`;
}

/** The small uppercase caption used above every fact's value — exported so a caller needing a
 *  non-text value (a Chip, e.g.) can pair it with `FactLabel` instead of duplicating the style. */
export function FactLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 2 }}>
      {children}
    </div>
  );
}

export function Fact({ label, value, mono, hint }: { label: string; value: string; mono?: boolean; hint?: string }) {
  const displayValue = mono ? truncateHash(value) : value;
  return (
    <div>
      <FactLabel>{label}</FactLabel>
      <div
        title={mono && displayValue !== value ? value : undefined}
        style={{ fontSize: theme.font.size.s, color: theme.color.text, wordBreak: "break-all", fontFamily: mono ? theme.font.mono : undefined }}
      >
        {displayValue}
      </div>
      {hint && <div style={{ color: theme.color.mute, fontSize: theme.font.size.xs, marginTop: 2 }}>{hint}</div>}
    </div>
  );
}
