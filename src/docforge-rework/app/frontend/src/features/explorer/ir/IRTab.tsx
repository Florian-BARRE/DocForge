// ====== Code Summary ======
// The document's raw structure in reading order — a type filter derived from the data, plus
// per-block rendering (figures inline with their enrichments, tables as real grids). Scrolls to
// and highlights the block a chunk card jumped from, when set (always clearing the filter first
// so the target block is guaranteed visible).

import { useEffect, useMemo, useRef, useState } from "react";
import type { DocumentIR, IREnrichment } from "../../../api/explorer";
import { theme } from "../../../theme";
import { BlockRow } from "./BlockRow";
import { BlockTypeFilter } from "./BlockTypeFilter";

interface IRTabProps {
  ir: DocumentIR;
  focusBlockId: string | null;
}

export function IRTab({ ir, focusBlockId }: IRTabProps) {
  const [typeFilter, setTypeFilter] = useState("all");
  const blockRefs = useRef(new Map<string, HTMLDivElement>());

  const types = useMemo(() => [...new Set(ir.blocks.map((b) => b.block_type))].sort(), [ir.blocks]);
  const figureByBlock = useMemo(() => new Map(ir.figures.map((f) => [f.block_id, f])), [ir.figures]);
  const tableByBlock = useMemo(() => new Map(ir.tables.map((t) => [t.block_id, t])), [ir.tables]);
  const enrichmentsByBlock = useMemo(() => {
    const map = new Map<string, IREnrichment[]>();
    for (const e of ir.enrichments) map.set(e.block_id, [...(map.get(e.block_id) ?? []), e]);
    return map;
  }, [ir.enrichments]);

  const sortedBlocks = useMemo(() => [...ir.blocks].sort((a, b) => a.reading_order - b.reading_order), [ir.blocks]);
  const visibleCount = typeFilter === "all" ? sortedBlocks.length : sortedBlocks.filter((b) => b.block_type === typeFilter).length;

  // A jump from the chunks tab always wins over an active filter that would otherwise hide it.
  useEffect(() => {
    if (focusBlockId) setTypeFilter("all");
  }, [focusBlockId]);

  // Re-run once the filter change above actually makes the target block visible.
  useEffect(() => {
    if (!focusBlockId) return;
    blockRefs.current.get(focusBlockId)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusBlockId, typeFilter]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <BlockTypeFilter types={types} active={typeFilter} onSelect={setTypeFilter} />
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{visibleCount} of {ir.blocks.length} block(s)</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {sortedBlocks.map((block) => (
          <BlockRow
            key={block.id}
            ref={(el) => {
              if (el) blockRefs.current.set(block.id, el);
              else blockRefs.current.delete(block.id);
            }}
            block={block}
            figure={figureByBlock.get(block.id)}
            table={tableByBlock.get(block.id)}
            enrichments={enrichmentsByBlock.get(block.id) ?? []}
            highlighted={block.id === focusBlockId}
            visible={typeFilter === "all" || block.block_type === typeFilter}
          />
        ))}
      </div>
    </div>
  );
}
