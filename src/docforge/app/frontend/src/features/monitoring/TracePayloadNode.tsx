// ====== Code Summary ======
// Recursive renderer for one node of an arbitrary trace payload (JSON of unknown depth/shape) — the
// walk `TracePayloadView`'s formatted mode drives. Renders content-hash blob references (keys like
// `render_blob_hash` / `source_hash` / `*_blob_hash`, or any bare 64-hex string — see
// `RecordTrace.strip_payloads`, which replaces raw bytes with `"<N bytes>"` placeholders but keeps
// the sibling content hashes) as a clickable `BlobRefChip` instead of an opaque string, long or
// multi-line strings as readable prose instead of an escaped one-liner, and everything else
// structurally (indented `key: value` / numbered items). Depth-capped and defensive — arbitrary/odd
// JSON never throws, it degrades to a raw `JSON.stringify` snippet instead.

import { theme } from "../../theme";
import { BlobRefChip } from "./BlobRefChip";

// Past this nesting depth, stop walking and fall back to raw JSON — a defensive ceiling against a
// pathologically deep/odd payload, not a limit real IR shapes are expected to hit.
const MAX_DEPTH = 12;
// A string this long (or containing a newline) reads better as a paragraph than an inline value.
const LONG_STRING_THRESHOLD = 120;

const HEX64_RE = /^[0-9a-f]{64}$/i;
const HASH_KEY_RE = /(^|_)hash$/i;
const BYTES_PLACEHOLDER_RE = /^<\d+ (bytes|numbers)>$/;
// Field-name hints that the referenced blob is an image (page render, figure crop, thumbnail) —
// gets an inline thumbnail instead of a plain view/download chip.
const IMAGE_HASH_KEY_RE = /(render|crop|thumbnail|image|page)[a-z_]*hash$/i;

function isBlobHashValue(key: string, value: string): boolean {
  return (HASH_KEY_RE.test(key) && value.length > 0) || HEX64_RE.test(value);
}

function safeStringify(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

const rowStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: theme.space.xs, padding: "2px 0",
};
const keyStyle: React.CSSProperties = {
  fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim, flex: "none",
};
const muteMonoStyle: React.CSSProperties = {
  fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute,
};
const nestStyle = (depth: number): React.CSSProperties => ({
  display: "flex", flexDirection: "column",
  marginLeft: depth > 0 ? theme.space.s : 0,
  borderLeft: depth > 0 ? `1px solid ${theme.color.line}` : "none",
  paddingLeft: depth > 0 ? theme.space.s : 0,
});

function StringValue({ fieldKey, value }: { fieldKey: string; value: string }) {
  if (isBlobHashValue(fieldKey, value)) {
    return <BlobRefChip hash={value} fieldName={fieldKey || "value"} image={IMAGE_HASH_KEY_RE.test(fieldKey)} />;
  }
  if (BYTES_PLACEHOLDER_RE.test(value)) {
    return <span style={muteMonoStyle}>{value}</span>;
  }
  if (value.length > LONG_STRING_THRESHOLD || value.includes("\n")) {
    return (
      <div
        style={{
          whiteSpace: "pre-wrap", wordBreak: "break-word", color: theme.color.text,
          fontSize: theme.font.size.xs, lineHeight: 1.5, background: theme.color.surface2,
          border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s,
          padding: theme.space.xs, maxWidth: "100%",
        }}
      >
        {value}
      </div>
    );
  }
  return <span style={{ fontSize: theme.font.size.xs, color: theme.color.text }}>{value}</span>;
}

interface TracePayloadNodeProps {
  /** The key this value was found under — "" at the root. Only used for hash-key detection + the
   *  blob chip's tooltip/download name, never rendered as its own label (the caller renders the
   *  `key:`/`[index]` prefix). */
  fieldKey: string;
  value: unknown;
  depth?: number;
}

export function TracePayloadNode({ fieldKey, value, depth = 0 }: TracePayloadNodeProps) {
  if (depth > MAX_DEPTH) return <span style={muteMonoStyle}>{safeStringify(value)}</span>;

  if (value === null || value === undefined) {
    return <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>—</span>;
  }

  if (typeof value === "string") return <StringValue fieldKey={fieldKey} value={value} />;

  if (typeof value === "number" || typeof value === "boolean") {
    return <span style={{ ...muteMonoStyle, color: theme.color.text }}>{String(value)}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>[]</span>;
    return (
      <div style={nestStyle(depth + 1)}>
        {value.map((item, index) => (
          <div key={index} style={rowStyle}>
            <span style={keyStyle}>[{index}]</span>
            <TracePayloadNode fieldKey={`${fieldKey}[${index}]`} value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>{"{}"}</span>;
    return (
      <div style={nestStyle(depth + 1)}>
        {entries.map(([key, item]) => (
          <div key={key} style={rowStyle}>
            <span style={keyStyle}>{key}:</span>
            <TracePayloadNode fieldKey={key} value={item} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }

  // Any other odd/unexpected JS value (function, symbol, bigint) — never thrown, just shown raw.
  return <span style={muteMonoStyle}>{safeStringify(value)}</span>;
}
