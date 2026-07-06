// ====== Code Summary ======
// The shared "loading…" placeholder — the same muted-text pattern already used inline in the
// pipeline studio, now reused across the collections and monitoring views.

import { theme } from "../theme";

export function LoadingState({ label }: { label: string }) {
  return <div style={{ padding: theme.space.l, color: theme.color.dim, fontSize: theme.font.size.s }}>{label}</div>;
}
