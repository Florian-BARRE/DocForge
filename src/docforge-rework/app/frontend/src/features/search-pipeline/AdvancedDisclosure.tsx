// ====== Code Summary ======
// A collapsed-by-default disclosure for the low-level node-config rail — built on the native
// <details>/<summary> pair (no JS state, no new dependency) so it degrades gracefully and needs no
// open/close wiring from the caller. Styled with theme tokens only, mirroring SearchControlRow.

import type { ReactNode } from "react";
import { theme } from "../../theme";

interface AdvancedDisclosureProps {
  summary: string;
  children: ReactNode;
}

export function AdvancedDisclosure({ summary, children }: AdvancedDisclosureProps) {
  return (
    <details
      style={{
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
        background: theme.color.surface, boxShadow: theme.shadow.sm,
      }}
    >
      <summary
        style={{
          cursor: "pointer", userSelect: "none", padding: theme.space.m,
          fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text,
          fontFamily: theme.font.display,
        }}
      >
        {summary}
      </summary>
      <div
        style={{
          padding: theme.space.m, paddingTop: 0,
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        {children}
      </div>
    </details>
  );
}
