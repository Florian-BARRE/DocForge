// ====== Code Summary ======
// One field row in the schema table — owns its own hover state (surface2 highlight) so
// SchemaTable itself can stay a plain, stateless list-of-rows.

import { useState } from "react";
import type { FieldSpec } from "../../api/collections";
import { Chip, type ChipTone } from "../../components/Chip";
import { theme as t } from "../../theme";

const cellStyle: React.CSSProperties = { padding: `${t.space.m}px ${t.space.m}px`, fontSize: t.font.size.l, verticalAlign: "middle" };

/** A tonal presence chip when the flag is on; a quiet dash when it isn't — keeps the row scannable. */
function flagChip(active: boolean, label: string, tone: ChipTone) {
  return active ? <Chip tone={tone}>{label}</Chip> : <span style={{ color: t.color.mute }}>–</span>;
}

// "generated"/"system" are still meaningfully distinct facts (an escalation-worthy provenance,
// a locked system field); "user" is just the plain/default case — capability-neutral, not forge.
const ORIGIN_TONE: Record<FieldSpec["origin"], ChipTone> = { generated: "loop", system: "warn", user: "capability" };

export function SchemaTableRow({ field }: { field: FieldSpec }) {
  const [hover, setHover] = useState(false);
  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ borderBottom: `1px solid ${t.color.line}`, background: hover ? t.color.surface2 : "transparent", transition: "background .12s ease" }}
    >
      <td style={{ ...cellStyle, fontFamily: t.font.mono, color: t.color.text }}>{field.field_name}</td>
      <td style={{ ...cellStyle, fontFamily: t.font.mono, color: t.color.dim }}>{field.field_type}</td>
      <td style={{ ...cellStyle, textAlign: "center" }}>{flagChip(field.required, "required", "capability")}</td>
      <td style={{ ...cellStyle, textAlign: "center" }}>{flagChip(field.filterable, "filter", "capability")}</td>
      <td style={{ ...cellStyle, textAlign: "center" }}>{flagChip(field.lexical, "lexical", "capability")}</td>
      <td style={{ ...cellStyle, textAlign: "center" }}>{flagChip(field.semantic, "semantic", "capability")}</td>
      <td style={cellStyle}>
        {field.enum_values?.length ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {field.enum_values.map((v) => <Chip key={v} tone="dim">{v}</Chip>)}
          </div>
        ) : (
          <span style={{ color: t.color.mute }}>—</span>
        )}
      </td>
      <td style={cellStyle}>
        <Chip tone={ORIGIN_TONE[field.origin]}>{field.origin}</Chip>
      </td>
      <td style={{ ...cellStyle, color: t.color.dim }}>{field.scope}</td>
    </tr>
  );
}
