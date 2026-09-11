// ====== Code Summary ======
// The dry-run's headline: ok/failed banner (a failed NODE is DATA, never an HTTP error — see
// api/preview.ts), the produced IR at a glance, the metered cost, and any non-fatal warnings.

import { humanizePreviewError } from "./previewErrorHumanize";
import type { PreviewResponse } from "../../../api/preview";
import { Chip } from "../../../components/Chip";
import { theme as t } from "../../../theme";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ color: t.color.mute, fontSize: t.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </span>
      <span style={{ color: t.color.text, fontSize: t.font.size.l, fontFamily: t.font.mono, fontWeight: t.font.weight.semibold }}>
        {value}
      </span>
    </div>
  );
}

export function PipelinePreviewSummary({ result }: { result: PreviewResponse }) {
  const cost = result.cost.cost_usd !== null ? `$${result.cost.cost_usd.toFixed(4)}` : `${(result.cost.prompt_tokens + result.cost.completion_tokens).toLocaleString()} tok`;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.m }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
        <Chip tone={result.ok ? "ok" : "error"}>{result.ok ? "ok" : "failed"}</Chip>
        <span style={{ color: t.color.text, fontSize: t.font.size.m, fontWeight: t.font.weight.semibold, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {result.source_filename}
        </span>
      </div>
      {!result.ok && result.error && (
        <div style={{ color: t.color.error, fontSize: t.font.size.s, background: t.color.errorSoft, borderRadius: t.radius.m, padding: t.space.s }}>
          {humanizePreviewError(result.error)}
          {result.failed_node_kind && (
            <span style={{ color: t.color.mute, marginLeft: t.space.xs, fontFamily: t.font.mono }}>({result.failed_node_kind})</span>
          )}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: t.space.m }}>
        {result.ir && <StatTile label="Pages" value={String(result.ir.page_count)} />}
        {result.ir && <StatTile label="Blocks" value={String(result.ir.block_count)} />}
        {result.ir && <StatTile label="Figures" value={String(result.ir.figure_count)} />}
        <StatTile label="Chunks" value={result.chunks_truncated ? `${result.chunk_count} (first ${result.chunks.length} shown)` : String(result.chunk_count)} />
        <StatTile label="Vector sets" value={String(result.vector_set_count)} />
        <StatTile label="Cost" value={cost} />
      </div>
      {result.ir && (
        <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>
          {result.ir.title || "(untitled)"} · {result.ir.language || "unknown language"} · {result.ir.source_format}
        </div>
      )}
      {result.warnings.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {result.warnings.map((warning, index) => (
            <div key={index} style={{ color: t.color.warnStrong, fontSize: t.font.size.s }}>
              ⚠ {warning}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
