// ====== Code Summary ======
// A chunk's source block ids as small jump links — clicking switches to the IR tab, scrolled to
// and highlighting that exact block.

import { theme } from "../../../theme";

function shortBlockLabel(blockId: string): string {
  return blockId.split(":").pop() || blockId;
}

interface ChunkBlockLinksProps {
  blockIds: string[];
  onJumpToBlock: (blockId: string) => void;
}

export function ChunkBlockLinks({ blockIds, onJumpToBlock }: ChunkBlockLinksProps) {
  if (!blockIds.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {blockIds.map((id) => (
        <button
          key={id}
          onClick={() => onJumpToBlock(id)}
          title={id}
          style={{
            background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
            color: theme.color.accentSafe, cursor: "pointer", fontSize: theme.font.size.xs,
            padding: "3px 8px", fontFamily: theme.font.mono,
          }}
        >
          {shortBlockLabel(id)}
        </button>
      ))}
    </div>
  );
}
