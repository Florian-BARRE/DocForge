// ====== Code Summary ======
// The first N chunks the dry-run produced, in reading order — the actual retrieval units a real
// ingestion would store, so the user can eyeball chunk boundaries/headings/context before committing.

import type { PreviewChunk } from "../../../api/preview";
import { Chip } from "../../../components/Chip";
import { theme as t } from "../../../theme";

function ChunkRow({ chunk }: { chunk: PreviewChunk }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.xs, padding: t.space.m, background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute }}>#{chunk.ordinal}</span>
        <Chip tone="neutral">{chunk.role}</Chip>
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.dim }}>{chunk.token_count} tok</span>
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.dim }}>p.{chunk.page_start}–{chunk.page_end}</span>
        {chunk.heading_path.length > 0 && (
          <span style={{ fontSize: t.font.size.xs, color: t.color.mute, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {chunk.heading_path.join(" › ")}
          </span>
        )}
      </div>
      <p style={{ margin: 0, color: t.color.text, fontSize: t.font.size.s, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
        {chunk.text}
        {chunk.text_truncated && <span style={{ color: t.color.mute }}> …</span>}
      </p>
    </div>
  );
}

export function PipelinePreviewChunks({ chunks }: { chunks: PreviewChunk[] }) {
  if (chunks.length === 0) {
    return <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>No chunk was produced.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.s }}>
      {chunks.map((chunk) => (
        <ChunkRow key={chunk.chunk_id} chunk={chunk} />
      ))}
    </div>
  );
}
