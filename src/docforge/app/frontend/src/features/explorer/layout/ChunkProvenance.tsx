// ====== Code Summary ======
// The embedded text of a chunk, shown as the SEQUENCE it was assembled from: each source IR block's
// contribution is a tinted line in that block's type colour (with a filled reading-order chip), and
// the pipeline-added glue between them (breadcrumb, contextual prefix) is a muted "added" line. This
// makes "which IR became which part of the chunk, and what was added" literally visible, colour-
// consistent with the page boxes + IR cards. Details of the added parts live in the provenance column.

import type { IREnrichment } from "../../../api/explorer";
import { theme } from "../../../theme";
import { blockStyle } from "./blockColors";
import { segmentChunkText, type ChunkMember } from "./chunkAssembly";

interface ChunkProvenanceProps {
  chunkText: string;
  members: ChunkMember[];
  enrichmentsByBlock: Map<string, IREnrichment[]>;
  strategy: string;
  tokenCount: number;
  /** The selected block's reading-order index — its segment is emphasised. */
  selectedBlockIndex: number | null;
}

export function ChunkProvenance({ chunkText, members, enrichmentsByBlock, strategy, tokenCount, selectedBlockIndex }: ChunkProvenanceProps) {
  const segments = segmentChunkText(chunkText, members, enrichmentsByBlock);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs, flexWrap: "wrap" }}>
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim }}>assembled from</span>
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.text }}>{strategy}</span>
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>· {tokenCount} tok</span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {segments.map((segment, i) => {
          if (segment.added) {
            const text = segment.text.trim();
            if (!text) return null;
            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  gap: theme.space.xs,
                  fontSize: theme.font.size.xs,
                  color: theme.color.dim,
                  fontStyle: "italic",
                  lineHeight: 1.45,
                }}
              >
                <span
                  style={{
                    flex: "none",
                    fontStyle: "normal",
                    fontFamily: theme.font.mono,
                    fontSize: 9,
                    letterSpacing: "0.03em",
                    textTransform: "uppercase",
                    color: theme.color.mute,
                    border: `1px dashed ${theme.color.lineStrong}`,
                    borderRadius: theme.radius.s,
                    padding: "0 4px",
                    height: "fit-content",
                    lineHeight: "15px",
                  }}
                >
                  added
                </span>
                <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{text}</span>
              </div>
            );
          }
          const style = blockStyle(segment.blockType ?? "");
          const emphasised = selectedBlockIndex != null && segment.blockIndex === selectedBlockIndex;
          const hue = emphasised ? theme.color.accent : style.color;
          return (
            <div
              key={i}
              style={{
                display: "flex",
                gap: theme.space.xs,
                fontSize: theme.font.size.s,
                color: theme.color.text,
                borderLeft: `3px solid ${hue}`,
                background: emphasised ? theme.color.accentSoft : `color-mix(in srgb, ${style.color} 6%, transparent)`,
                borderRadius: `0 ${theme.radius.s}px ${theme.radius.s}px 0`,
                padding: `3px ${theme.space.s}px`,
                lineHeight: 1.45,
              }}
            >
              <span
                style={{
                  flex: "none",
                  fontFamily: theme.font.mono,
                  fontSize: 9,
                  fontWeight: theme.font.weight.semibold,
                  color: theme.color.onAccent,
                  background: hue,
                  borderRadius: theme.radius.s,
                  padding: "0 4px",
                  height: "fit-content",
                  lineHeight: "15px",
                }}
              >
                {(segment.blockIndex ?? 0) + 1}
              </span>
              <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{segment.text.trim()}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
