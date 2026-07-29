// ====== Code Summary ======
// One IR block in reading order — a type chip, its page, and either its native text (headings
// rendered stronger by level), a figure's crop + enrichments, or a table's rendered grid.
// Always mounted regardless of the active type filter (`visible` toggles display only) so a jump
// from the chunks tab can scroll to it even if it was filtered out a moment ago.

import { forwardRef } from "react";
import type { IREnrichment, IRBlock, IRFigure, IRTable } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { FigureBlock } from "./FigureBlock";
import { TableBlock } from "./TableBlock";

interface BlockRowProps {
  block: IRBlock;
  figure?: IRFigure;
  table?: IRTable;
  enrichments: IREnrichment[];
  highlighted: boolean;
  visible: boolean;
}

function headingStyle(level: number | null): React.CSSProperties {
  if (level === null) return { fontSize: theme.font.size.m };
  const sizeByLevel: Record<number, number> = { 1: theme.font.size.xl, 2: theme.font.size.l, 3: theme.font.size.m };
  return { fontFamily: theme.font.display, fontSize: sizeByLevel[level] ?? theme.font.size.m, fontWeight: 700 };
}

export const BlockRow = forwardRef<HTMLDivElement, BlockRowProps>(function BlockRow(
  { block, figure, table, enrichments, highlighted, visible },
  ref,
) {
  return (
    <div
      ref={ref}
      style={{
        display: visible ? "flex" : "none", flexDirection: "column", gap: 8, padding: theme.space.m,
        borderRadius: theme.radius.m,
        background: highlighted ? theme.color.accentSoft : theme.color.surface,
        border: `1px solid ${highlighted ? theme.color.accentLine : theme.color.line}`,
        borderLeft: `3px solid ${highlighted ? theme.color.accent : "transparent"}`,
        transition: "background .2s ease, border-color .2s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Chip tone={block.block_type === "figure" ? "loop" : block.block_type === "table" ? "warn" : "dim"}>
          {block.block_type}
        </Chip>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}>
          page {displayPage(block.page)}
        </span>
        {block.is_boilerplate && <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>boilerplate</span>}
      </div>

      {block.block_type === "figure" ? (
        <FigureBlock figure={figure} enrichments={enrichments} />
      ) : block.block_type === "table" && table ? (
        <TableBlock table={table} />
      ) : (
        block.text && (
          <div style={block.block_type === "heading" ? headingStyle(block.level) : { fontSize: theme.font.size.s, color: theme.color.text }}>
            {block.text}
          </div>
        )
      )}
    </div>
  );
});
