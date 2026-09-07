// ====== Code Summary ======
// Renders one trace node's fetched full payload (`JobEventPayload.payload`, arbitrary JSON) — walks
// it via `TracePayloadNode` so content-hash blob references become clickable and long text reads as
// prose, with a "Raw JSON" toggle for power users who want the untouched dump. Delegated to by
// `JobEventPayloadButton`, which keeps owning the load/loading/error/truncated/empty states — this
// component only ever receives an already-loaded payload.

import { useState } from "react";
import { theme } from "../../theme";
import { TracePayloadNode } from "./TracePayloadNode";

interface TracePayloadViewProps {
  payload: unknown;
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function TracePayloadView({ payload }: TracePayloadViewProps) {
  const [raw, setRaw] = useState(false);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, maxWidth: "100%" }}>
      <button
        type="button"
        onClick={() => setRaw((prev) => !prev)}
        style={{
          alignSelf: "flex-start", background: "none", border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.pill, color: theme.color.mute, cursor: "pointer",
          fontSize: theme.font.size.xs, padding: "2px 9px",
        }}
      >
        {raw ? "Formatted view" : "Raw JSON"}
      </button>
      {raw ? (
        <pre
          style={{
            margin: 0, maxWidth: "100%", maxHeight: 320, overflow: "auto",
            background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.s, padding: theme.space.s,
            fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.text,
          }}
        >
          {safeStringify(payload)}
        </pre>
      ) : (
        <div style={{ maxWidth: "100%", maxHeight: 320, overflow: "auto" }}>
          <TracePayloadNode fieldKey="" value={payload} />
        </div>
      )}
    </div>
  );
}
