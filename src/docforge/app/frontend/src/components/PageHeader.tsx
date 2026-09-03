// ====== Code Summary ======
// The shared page header: an optional eyebrow (back link / context), a display-face title, an
// optional subtitle line, and a right-aligned actions slot. One consistent header across every
// page gives the app a clear, legible information hierarchy.

import type { ReactNode } from "react";
import { theme as t } from "../theme";

interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  /** A denser header for pages nested under a lot of chrome (collection + document views) — smaller
   *  title and tighter margins so the actual content gets more vertical room. */
  compact?: boolean;
}

export function PageHeader({ title, subtitle, eyebrow, actions, compact }: PageHeaderProps) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: t.space.l, marginBottom: compact ? t.space.m : t.space.xl }}>
      <div style={{ minWidth: 0 }}>
        {eyebrow && <div style={{ marginBottom: compact ? 2 : t.space.s }}>{eyebrow}</div>}
        <h1
          style={{
            fontFamily: t.font.display, fontWeight: 700, fontSize: compact ? t.font.size.xxl : t.font.size.display,
            letterSpacing: "-0.02em", color: t.color.text, lineHeight: 1.1,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <div style={{ color: t.color.dim, fontSize: compact ? t.font.size.m : t.font.size.l, marginTop: compact ? 3 : 6 }}>{subtitle}</div>
        )}
      </div>
      {actions && (
        <div style={{ marginLeft: "auto", display: "flex", flexWrap: "wrap", gap: t.space.s, minWidth: 0 }}>
          {actions}
        </div>
      )}
    </div>
  );
}
