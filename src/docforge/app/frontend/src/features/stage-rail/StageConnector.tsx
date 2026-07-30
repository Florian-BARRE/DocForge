// ====== Code Summary ======
// The thin vertical thread drawn between two consecutive stage cards — reinforces that the rail is
// a single ordered run, not a loose stack of independent cards. Purely decorative (no props, no
// state) so it can be dropped between `StageCard`s without touching the rail's data flow.

import { theme } from "../../theme";

export function StageConnector() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", paddingLeft: theme.space.l + 16 }}>
      <div style={{ width: 2, height: theme.space.l, background: `linear-gradient(${theme.color.lineStrong}, ${theme.color.line})` }} />
    </div>
  );
}
