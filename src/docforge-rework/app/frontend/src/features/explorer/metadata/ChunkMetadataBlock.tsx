// ====== Code Summary ======
// A chunk's metadata list — generated string-array fields (the metagen atomic propositions) get
// the showcase treatment, everything else falls back to a compact field:value line.

import type { MetadataValue } from "../../../api/explorer";
import { theme } from "../../../theme";
import { GeneratedFactsList } from "./GeneratedFactsList";
import { ValueRenderer } from "./ValueRenderer";

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

export function ChunkMetadataBlock({ metadata }: { metadata: MetadataValue[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      {metadata.map((m) =>
        m.origin === "generated" && isStringArray(m.value) ? (
          <GeneratedFactsList key={m.field_name} fieldName={m.field_name} facts={m.value} />
        ) : (
          <div key={m.field_name} style={{ display: "flex", gap: theme.space.s, fontSize: theme.font.size.s }}>
            <span style={{ color: theme.color.dim, fontFamily: theme.font.mono }}>{m.field_name}:</span>
            <ValueRenderer value={m.value} />
          </div>
        ),
      )}
    </div>
  );
}
