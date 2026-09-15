// ====== Code Summary ======
// A titled block used to visually separate the Settings page's three sections (Contract / Transfer
// / Danger zone) — just a heading + optional description above whatever the section renders, so
// each section reads as a deliberate, named part of the page rather than an unlabeled stack of
// unrelated cards.

import type { ReactNode } from "react";
import { theme } from "../../../theme";

interface SettingsSectionProps {
  title: string;
  description?: string;
  children: ReactNode;
}

export function SettingsSection({ title, description, children }: SettingsSectionProps) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div>
        <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.bold, color: theme.color.text, margin: 0 }}>
          {title}
        </h2>
        {description && (
          <p style={{ color: theme.color.dim, fontSize: theme.font.size.s, margin: `${theme.space.xs}px 0 0` }}>
            {description}
          </p>
        )}
      </div>
      {children}
    </section>
  );
}
