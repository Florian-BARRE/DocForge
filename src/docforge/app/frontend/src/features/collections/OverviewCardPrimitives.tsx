// ====== Code Summary ======
// Shared presentational primitives for the collection Overview dashboard — a headline stat tile,
// a titled card with an "Open →" affordance, and a label/value row. Grouped in one file because
// they form a single small visual kit reused across every Overview card (health, jobs, documents,
// metadata, pipeline, search) rather than distinct standalone components.

import type { ReactNode } from "react";
import { Button } from "../../components/Button";
import { theme as t } from "../../theme";

/** A headline metric tile — a label, a big value, and an optional supporting line. */
export function StatTile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, padding: t.space.l, boxShadow: t.shadow.sm }}>
      <div style={{ color: t.color.dim, fontSize: t.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontFamily: t.font.display, fontWeight: 700, fontSize: 26, color: t.color.text, marginTop: 6, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ color: t.color.dim, fontSize: t.font.size.m, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

/** A titled card with an "Open →" affordance to the relevant tab, wrapping arbitrary summary content. */
export function SummaryCard({ title, onOpen, children }: { title: string; onOpen: () => void; children: ReactNode }) {
  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, padding: t.space.l, boxShadow: t.shadow.sm, display: "flex", flexDirection: "column", gap: t.space.m }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <span style={{ fontFamily: t.font.display, fontWeight: 600, fontSize: t.font.size.xl, color: t.color.text }}>{title}</span>
        <div style={{ marginLeft: "auto" }}><Button size="sm" variant="ghost" onClick={onOpen}>Open →</Button></div>
      </div>
      {children}
    </div>
  );
}

/** A simple label/value line inside a `SummaryCard`. */
export function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: t.space.m }}>
      <span style={{ color: t.color.dim, fontSize: t.font.size.m, minWidth: 120 }}>{label}</span>
      <span style={{ color: t.color.text, fontSize: t.font.size.l }}>{value}</span>
    </div>
  );
}

/** A compact clickable stat — a quick-glance number with a link out to the tab that owns it. */
export function StatChip({ label, value, sub, onClick }: { label: string; value: ReactNode; sub?: ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "flex", flexDirection: "column", gap: 2, textAlign: "left", flex: "1 1 150px", minWidth: 140,
        background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m,
        padding: `${t.space.s}px ${t.space.m}px`, cursor: "pointer", font: "inherit",
      }}
    >
      <span style={{ color: t.color.mute, fontSize: t.font.size.xs, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</span>
      <span style={{ fontFamily: t.font.display, fontWeight: 700, fontSize: t.font.size.xl, color: t.color.text }}>{value}</span>
      {sub && <span style={{ color: t.color.dim, fontSize: t.font.size.xs }}>{sub}</span>}
    </button>
  );
}
