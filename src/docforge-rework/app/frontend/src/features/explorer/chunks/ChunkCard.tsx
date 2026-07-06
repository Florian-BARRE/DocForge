// ====== Code Summary ======
// One chunk's full card — index, size, indexed flag, its text, generated metadata and the source
// blocks it was assembled from.

import type { ChunkInfo } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { ChunkMetadataBlock } from "../metadata/ChunkMetadataBlock";
import { ChunkBlockLinks } from "./ChunkBlockLinks";
import { ChunkText } from "./ChunkText";

interface ChunkCardProps {
  chunk: ChunkInfo;
  onJumpToBlock: (blockId: string) => void;
}

export function ChunkCard({ chunk, onJumpToBlock }: ChunkCardProps) {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: theme.space.m,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong style={{ fontSize: theme.font.size.m }}>#{chunk.chunk_index}</strong>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chunk.token_count} tokens</span>
        <Chip tone={chunk.is_indexed ? "ok" : "dim"}>{chunk.is_indexed ? "indexed" : "not indexed"}</Chip>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{chunk.strategy}</span>
      </div>

      <ChunkText text={chunk.text} />

      {chunk.metadata.length > 0 && <ChunkMetadataBlock metadata={chunk.metadata} />}

      {chunk.block_ids.length > 0 && (
        <div style={{ borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.s }}>
          <ChunkBlockLinks blockIds={chunk.block_ids} onJumpToBlock={onJumpToBlock} />
        </div>
      )}
    </div>
  );
}
