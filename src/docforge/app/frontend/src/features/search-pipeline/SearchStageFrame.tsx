// ====== Code Summary ======
// The search rail's card frame — the SAME shape as the ingestion StageCard (accent left edge, a
// left control slot, title + family tag, description, and an indented body) so both pipelines read
// as one visual language. Read-only steps put a step number in the slot; the reranking step puts a
// switch; the query-transform step puts a wider segmented selector — a 2-column CSS grid (left slot
// sized to its own content, floor 34px) keeps every control's width self-determined while the title
// and the indented body still line up under the SAME column, however wide that control gets.

import type { ReactNode } from "react";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";

interface SearchStageFrameProps {
  /** The left control slot — a step-number badge or a StageSwitch. */
  left: ReactNode;
  title: string;
  /** The node family, shown as the quiet mono tag. */
  tag?: string;
  summary?: string;
  /** A muted right-aligned caption (e.g. "read-only"). */
  rightNote?: string;
  /** Dims the card + hides the accent edge when a toggleable step is off. */
  enabled?: boolean;
  children?: ReactNode;
}

export function SearchStageFrame({ left, title, tag, summary, rightNote, enabled = true, children }: SearchStageFrameProps) {
  return (
    <div
      className="df-hover"
      style={{
        position: "relative", overflow: "hidden",
        background: t.color.surface, border: `1px solid ${t.color.line}`,
        borderRadius: t.radius.l, padding: t.space.l,
        opacity: enabled ? 1 : 0.6,
        display: "grid", gridTemplateColumns: "minmax(34px, max-content) 1fr",
        columnGap: t.space.m, rowGap: t.space.s,
        boxShadow: t.shadow.sm,
      }}
    >
      {/* Left accent hairline — reads "active pipeline step" at a glance (mirrors StageCard). */}
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: enabled ? t.color.accent : "transparent" }} />
      <div style={{ display: "flex", justifyContent: "center", paddingTop: 1 }}>{left}</div>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
          <strong style={{ fontFamily: t.font.display, fontSize: t.font.size.xl, fontWeight: 700 }}>{title}</strong>
          {tag && <Chip tone="dim"><span style={{ fontFamily: t.font.mono }}>{tag}</span></Chip>}
          {rightNote && (
            <span
              title="This step has no knobs — it runs as configured by the pipeline."
              style={{ marginLeft: "auto", color: t.color.mute, fontSize: t.font.size.xs, fontWeight: 500, letterSpacing: "0.02em", whiteSpace: "nowrap" }}
            >
              {rightNote}
            </span>
          )}
        </div>
        {summary && <div style={{ color: t.color.dim, fontSize: t.font.size.s, marginTop: 2 }}>{summary}</div>}
      </div>
      {/* Placed explicitly in column 2 so it lines up under the title regardless of the left slot's width. */}
      {children && <div style={{ gridColumn: 2 }}>{children}</div>}
    </div>
  );
}
