// ====== Code Summary ======
// The shared empty-state hero — a light glyph, a title, an optional subtitle, an optional primary
// action, and optional extra content underneath (a form, a checklist…). Used wherever a zero-result
// page/section would otherwise show a wall of "0" stats: replaces the dead placeholder with a clear
// next step. Deliberately generic (no feature-domain types) so any feature can reuse it.

import type { ReactNode } from "react";
import { theme as t } from "../theme";

interface EmptyStateProps {
  /** A short glyph/initial rendered in the accent monogram (defaults to "+"). */
  icon?: ReactNode;
  title: string;
  subtitle?: ReactNode;
  /** The primary call to action (usually a `<Button variant="primary">`). */
  action?: ReactNode;
  /** Extra content below the action — an inline form, a "what happens next" list, etc. */
  children?: ReactNode;
}

export function EmptyState({ icon, title, subtitle, action, children }: EmptyStateProps) {
  return (
    <div
      className="df-rise"
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center",
        gap: t.space.m, padding: `${t.space.xxl}px ${t.space.xl}px`,
        background: t.color.surface, border: `1px dashed ${t.color.lineStrong}`, borderRadius: t.radius.l,
      }}
    >
      <span
        style={{
          width: 48, height: 48, borderRadius: t.radius.pill, display: "grid", placeItems: "center",
          background: t.color.accentSoft, color: t.color.accentSafe,
          fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xxl,
        }}
      >
        {icon ?? "+"}
      </span>
      <div style={{ fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xl, color: t.color.text }}>
        {title}
      </div>
      {subtitle && (
        <div style={{ color: t.color.dim, fontSize: t.font.size.m, maxWidth: 440 }}>{subtitle}</div>
      )}
      {action && <div>{action}</div>}
      {children && <div style={{ width: "100%", maxWidth: 480, textAlign: "left" }}>{children}</div>}
    </div>
  );
}
