// ====== Code Summary ======
// One node of the dry-run's execution trace — status marker + kind + duration + score + the
// humanized failure reason on a failed node. Indent mirrors `depth` (nested/ForEach-item nodes),
// the same materialized-path idea as the job monitor's JobEventItem, kept local (not cross-imported,
// see feature_slice_isolation.md) since the shapes (PreviewTraceNode vs JobEvent) differ.

import { humanizePreviewError } from "./previewErrorHumanize";
import type { PreviewTraceNode } from "../../../api/preview";
import { theme as t } from "../../../theme";

const INDENT_PER_DEPTH = t.space.xl;

const NODE_COLOR_BY_STATUS: Record<string, string> = {
  success: t.color.ok,
  failed: t.color.error,
  skipped: t.color.mute,
};

export function PipelinePreviewTraceRow({ node }: { node: PreviewTraceNode }) {
  const color = NODE_COLOR_BY_STATUS[node.status] ?? t.color.dim;
  return (
    <div
      style={{
        display: "flex", flexWrap: "wrap", alignItems: "center", gap: t.space.s,
        padding: `${t.space.xs}px 0`, borderLeft: `2px solid ${t.color.line}`,
        paddingLeft: t.space.m, marginLeft: node.depth * INDENT_PER_DEPTH, position: "relative",
      }}
    >
      <span
        style={{
          position: "absolute", left: -6, top: t.space.xs + 4, width: 10, height: 10,
          borderRadius: t.radius.pill, background: color, boxShadow: `0 0 0 3px ${t.color.bg}`,
        }}
      />
      <span style={{ fontSize: t.font.size.s, color: t.color.text, minWidth: 120 }}>{node.node_id}</span>
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute }}>{node.kind}</span>
      {node.item_index !== null && (
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.dim }}>item[{node.item_index}]</span>
      )}
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.dim }}>{(node.duration_ms / 1000).toFixed(2)}s</span>
      {node.score !== null && (
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute }}>score {node.score.toFixed(2)}</span>
      )}
      {node.status === "failed" && node.error_message && (
        <span style={{ color: t.color.error, fontSize: t.font.size.xs }}>
          {humanizePreviewError(node.error_message)}
        </span>
      )}
    </div>
  );
}
