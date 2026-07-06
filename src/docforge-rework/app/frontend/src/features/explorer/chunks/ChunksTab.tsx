// ====== Code Summary ======
// A document's chunks, in index order — each rendered as a full card.

import type { ChunkInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { ChunkCard } from "./ChunkCard";

interface ChunksTabProps {
  chunks: ChunkInfo[];
  onJumpToBlock: (blockId: string) => void;
}

export function ChunksTab({ chunks, onJumpToBlock }: ChunksTabProps) {
  if (!chunks.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No chunks recorded.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      {chunks.map((chunk) => (
        <ChunkCard key={chunk.id} chunk={chunk} onJumpToBlock={onJumpToBlock} />
      ))}
    </div>
  );
}
