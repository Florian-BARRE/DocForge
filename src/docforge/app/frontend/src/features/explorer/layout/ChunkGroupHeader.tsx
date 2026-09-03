// ====== Code Summary ======
// The header of a chunk grouping in the Layout view's reading-order panel: it names the retrieval
// chunk that a run of blocks was folded into — its index, structural role, token budget, section
// breadcrumb and whether it is searchable. It answers "these blocks became THIS chunk" so the raw
// IR (left/boxes) and the retrieval unit (the chunk) are visible side by side.

import type { ChunkInfo } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { ChunkHeadingPath } from "../chunks/ChunkHeadingPath";
import { ChunkRoleBadge } from "../chunks/ChunkRoleBadge";
import { theme } from "../../../theme";

interface ChunkGroupHeaderProps {
  chunk: ChunkInfo;
}

export function ChunkGroupHeader({ chunk }: ChunkGroupHeaderProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexWrap: "wrap" }}>
        <span
          style={{
            fontFamily: theme.font.mono,
            fontSize: theme.font.size.xs,
            fontWeight: theme.font.weight.semibold,
            color: theme.color.text,
          }}
        >
          Chunk #{chunk.chunk_index}
        </span>
        <ChunkRoleBadge role={chunk.role} />
        <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
          {chunk.token_count} tok
        </span>
        {chunk.enabled ? (
          <Chip tone="ok" title="This chunk is searchable">
            in search
          </Chip>
        ) : (
          <Chip tone="dim" title="This chunk is hidden from search">
            hidden
          </Chip>
        )}
      </div>
      <ChunkHeadingPath headingPath={chunk.heading_path} />
    </div>
  );
}
