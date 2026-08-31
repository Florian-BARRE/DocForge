// ====== Code Summary ======
// One chunk's full card — index, size, indexed flag, structural role, enable/disable toggle, its
// heading breadcrumb, text, generated metadata, the source blocks it was assembled from, and a
// collapsed-by-default details disclosure (id/parent/page/char count). Greyed out while its
// effective state is disabled.

import { useState } from "react";
import type { ChunkInfo } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { ChunkMetadataBlock } from "../metadata/ChunkMetadataBlock";
import { ChunkBlockLinks } from "./ChunkBlockLinks";
import { ChunkDetails } from "./ChunkDetails";
import { ChunkEnabledToggle } from "./ChunkEnabledToggle";
import { ChunkRoleBadge } from "./ChunkRoleBadge";
import { ChunkText } from "./ChunkText";

interface ChunkCardProps {
  chunk: ChunkInfo;
  selected: boolean;
  onToggleSelect: (chunkId: string) => void;
  onJumpToBlock: (blockId: string) => void;
  onEnabledChanged: (chunkId: string, enabled: boolean) => void;
  /** Open the chunk's source page with a box around its blocks — absent until IR + pages resolve. */
  onShowOnPage?: (chunk: ChunkInfo) => void;
}

export function ChunkCard({ chunk, selected, onToggleSelect, onJumpToBlock, onEnabledChanged, onShowOnPage }: ChunkCardProps) {
  const [reindexNote, setReindexNote] = useState(false);

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.surface, border: `1px solid ${selected ? theme.color.accentLine : theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m, boxShadow: theme.shadow.sm,
        opacity: chunk.enabled ? 1 : 0.55, transition: "border-color .15s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
        <input type="checkbox" checked={selected} onChange={() => onToggleSelect(chunk.id)} />
        <strong style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.m, color: theme.color.text }}>#{chunk.chunk_index}</strong>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
          {chunk.token_count} tokens · {chunk.text.length.toLocaleString()} chars
        </span>
        <Chip tone={chunk.is_indexed ? "ok" : "dim"}>{chunk.is_indexed ? "indexed" : "not indexed"}</Chip>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chunk.strategy}</span>
        <ChunkRoleBadge role={chunk.role} />
        {chunk.page !== null && <Chip tone="dim">page {displayPage(chunk.page)}</Chip>}
        {!chunk.enabled && <Chip tone="warn">disabled</Chip>}
        <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: theme.space.s }}>
          {onShowOnPage && chunk.block_ids.length > 0 && (
            <button
              onClick={() => onShowOnPage(chunk)}
              title="Show this chunk on its source page"
              style={{
                background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
                color: theme.color.accent, cursor: "pointer", fontSize: theme.font.size.xs, padding: "3px 8px",
              }}
            >
              view on page
            </button>
          )}
          <ChunkEnabledToggle
            chunkId={chunk.id}
            enabled={chunk.enabled}
            onChanged={(enabled, reindexRequired) => {
              onEnabledChanged(chunk.id, enabled);
              setReindexNote(reindexRequired);
            }}
          />
        </span>
      </div>

      {reindexNote && (
        <div style={{ color: theme.color.warn, fontSize: theme.font.size.xs }}>
          Enabled, but this chunk was never embedded — it won't be searchable until re-indexed.
        </div>
      )}

      <ChunkText text={chunk.text} />

      {chunk.metadata.length > 0 && <ChunkMetadataBlock metadata={chunk.metadata} />}

      {chunk.block_ids.length > 0 && (
        <div style={{ borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.s }}>
          <ChunkBlockLinks blockIds={chunk.block_ids} onJumpToBlock={onJumpToBlock} />
        </div>
      )}

      <div style={{ borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.s }}>
        <ChunkDetails
          id={chunk.id}
          parentId={chunk.parent_id}
          headingPath={chunk.heading_path}
          charCount={chunk.text.length}
          blockCount={chunk.block_ids.length}
          page={chunk.page}
        />
      </div>
    </div>
  );
}
