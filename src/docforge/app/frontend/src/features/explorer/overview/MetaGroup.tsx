// ====== Code Summary ======
// A subsection of the System metadata panel — a small uppercase heading over a responsive
// label/value grid. Kept as its own file so SystemMetadataPanel stays a plain list of groups.

import type { ReactNode } from "react";
import { theme } from "../../../theme";

export function MetaGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div
        style={{
          fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.mute,
          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: theme.space.s,
        }}
      >
        {title}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: theme.space.l }}>
        {children}
      </div>
    </div>
  );
}
