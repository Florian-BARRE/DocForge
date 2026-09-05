// ====== Code Summary ======
// One chunk in the Layout view's chunk column: header (index, role, tokens, searchability, section),
// its embedded text shown as the SEQUENCE of source-IR contributions (coloured per block type) with
// the added glue marked, and — below — a colour-coded provenance panel making explicit what was ADDED
// (breadcrumb/context), what was DEDUCED (generated metadata) and what was FOLDED (figure OCR/VLM),
// each with the stage · method it came from. All provenance lives here (no separate column). Click-
// selectable; strands from its member IRs bundle into it, coloured by type.

import { useState } from "react";

import type { IREnrichment, IRTable } from "../../../api/explorer";
import type { ChunkInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { ChunkGroupHeader } from "./ChunkGroupHeader";
import { ChunkProvenance } from "./ChunkProvenance";
import { chunkProvenance, type ChunkMember, type ProvenanceItem } from "./chunkAssembly";

interface ChunkColumnCardProps {
  chunk: ChunkInfo;
  members: ChunkMember[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  tablesByBlock: Map<string, IRTable>;
  selected: boolean;
  selectedBlockIndex: number | null;
  onSelect: () => void;
}

// How each provenance kind reads: its human category, and its colour code.
const PROV_META: Record<ProvenanceItem["kind"], { category: string; color: string }> = {
  breadcrumb: { category: "added", color: theme.color.info },
  enrichment: { category: "folded", color: theme.color.irisStrong },
  metadata: { category: "deduced", color: theme.color.okStrong },
};

function ProvenancePanel({ items }: { items: ProvenanceItem[] }) {
  if (items.length === 0) {
    return (
      <div style={{ fontSize: theme.font.size.xs, color: theme.color.mute, fontStyle: "italic" }}>
        Nothing added — raw blocks verbatim.
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.xs }}>
      <span style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.dim, textTransform: "uppercase", letterSpacing: "0.05em" }}>
        Added · deduced · from
      </span>
      {items.map((item) => {
        const meta = PROV_META[item.kind];
        return (
          <div key={item.id} style={{ display: "flex", gap: theme.space.xs }}>
            <span style={{ flex: "none", width: 7, height: 7, borderRadius: "50%", background: meta.color, marginTop: 5 }} aria-hidden="true" />
            <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs, flexWrap: "wrap" }}>
                <span style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.medium, color: meta.color, textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {meta.category}
                </span>
                <span style={{ fontSize: theme.font.size.xs, color: theme.color.text, wordBreak: "break-word", lineHeight: 1.35 }}>{item.label}</span>
              </div>
              <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
                {item.stage} · {item.method}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function ChunkColumnCard({ chunk, members, enrichmentsByBlock, tablesByBlock, selected, selectedBlockIndex, onSelect }: ChunkColumnCardProps) {
  const [hovered, setHovered] = useState(false);
  const edge = selected ? theme.color.accent : hovered ? theme.color.accentLine : theme.color.lineStrong;
  const provItems = chunkProvenance(chunk, members, enrichmentsByBlock);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: theme.space.s,
        padding: theme.space.m,
        borderRadius: theme.radius.m,
        borderTop: `${selected ? 2 : 1}px solid ${edge}`,
        borderRight: `${selected ? 2 : 1}px solid ${edge}`,
        borderBottom: `${selected ? 2 : 1}px solid ${edge}`,
        borderLeft: `4px solid ${edge}`,
        background: selected ? theme.color.surface2 : theme.color.panel,
        boxShadow: selected ? theme.shadow.sm : "none",
        cursor: "pointer",
        transition: "border-color .12s ease, background .12s ease, box-shadow .12s ease",
      }}
    >
      <ChunkGroupHeader chunk={chunk} />
      <ChunkProvenance
        chunkText={chunk.text}
        members={members}
        enrichmentsByBlock={enrichmentsByBlock}
        tablesByBlock={tablesByBlock}
        strategy={chunk.strategy}
        tokenCount={chunk.token_count}
        selectedBlockIndex={selectedBlockIndex}
      />
      <ProvenancePanel items={provItems} />
    </div>
  );
}
