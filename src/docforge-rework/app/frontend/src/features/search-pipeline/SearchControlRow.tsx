// ====== Code Summary ======
// One plain title/description/control row — the shared shape of the simple search controls
// (fusion summary + rerank toggle). Kept tiny and generic so SearchSimpleControls stays a pure
// layout of two rows.

import type { ReactNode } from "react";
import { theme } from "../../theme";

interface SearchControlRowProps {
  title: string;
  description: string;
  control: ReactNode;
}

export function SearchControlRow({ title, description, control }: SearchControlRowProps) {
  return (
    <div
      style={{
        display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: theme.space.l,
        padding: theme.space.m,
        background: theme.color.card, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
      }}
    >
      <div>
        <div style={{ fontSize: theme.font.size.l, fontWeight: 600 }}>{title}</div>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginTop: 2 }}>{description}</div>
      </div>
      {control}
    </div>
  );
}
