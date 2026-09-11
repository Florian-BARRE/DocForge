// ====== Code Summary ======
// The dry-run's full per-node execution trace, roots first — lets the user see exactly where a
// failed run died, or how each stage scored/timed on a successful one.

import type { PreviewTraceNode } from "../../../api/preview";
import { theme as t } from "../../../theme";
import { PipelinePreviewTraceRow } from "./PipelinePreviewTraceRow";

export function PipelinePreviewTrace({ trace }: { trace: PreviewTraceNode[] }) {
  if (trace.length === 0) {
    return <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>No node ran.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {trace.map((node) => (
        <PipelinePreviewTraceRow key={node.node_path} node={node} />
      ))}
    </div>
  );
}
