// ====== Code Summary ======
// A document's chunks, in index order — each rendered as a full card, with a multi-select bulk
// enable/disable bar above them (the explorer's only bulk toggle surface).

import { useState } from "react";
import { setChunksEnabled, type ChunkInfo } from "../../../api/explorer";
import { theme } from "../../../theme";
import { ChunkBulkActions } from "./ChunkBulkActions";
import { ChunkCard } from "./ChunkCard";

interface ChunksTabProps {
  chunks: ChunkInfo[];
  onJumpToBlock: (blockId: string) => void;
  onChunkEnabledChanged: (chunkId: string, enabled: boolean) => void;
}

export function ChunksTab({ chunks, onJumpToBlock, onChunkEnabledChanged }: ChunksTabProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleSelect = (chunkId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  };

  const applyBulk = async (enabled: boolean) => {
    const response = await setChunksEnabled(Array.from(selected), enabled);
    for (const result of response.results) onChunkEnabledChanged(result.chunk_id, result.enabled);
    setSelected(new Set());
    return response;
  };

  if (!chunks.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No chunks recorded.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <ChunkBulkActions selectedCount={selected.size} onApply={applyBulk} />
      {chunks.map((chunk) => (
        <ChunkCard
          key={chunk.id}
          chunk={chunk}
          selected={selected.has(chunk.id)}
          onToggleSelect={toggleSelect}
          onJumpToBlock={onJumpToBlock}
          onEnabledChanged={onChunkEnabledChanged}
        />
      ))}
    </div>
  );
}
