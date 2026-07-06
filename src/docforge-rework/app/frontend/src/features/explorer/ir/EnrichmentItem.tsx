// ====== Code Summary ======
// One enrichment applied to a block — kind chip, status chip, and its text/structured result.

import type { IREnrichment } from "../../../api/explorer";
import { Chip, type ChipTone } from "../../../components/Chip";
import { theme } from "../../../theme";

const STATUS_TONE: Record<IREnrichment["status"], ChipTone> = {
  ok: "ok",
  failed: "error",
  skipped: "dim",
};

export function EnrichmentItem({ enrichment }: { enrichment: IREnrichment }) {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: 2,
        background: theme.color.bg, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.s, padding: `${theme.space.xs}px ${theme.space.s}px`,
      }}
    >
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <Chip tone="accent">{enrichment.kind}</Chip>
        <Chip tone={STATUS_TONE[enrichment.status]}>{enrichment.status}</Chip>
      </div>
      {enrichment.text && <div style={{ fontSize: theme.font.size.s }}>{enrichment.text}</div>}
      {enrichment.data !== null && enrichment.data !== undefined && (
        <code style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          {JSON.stringify(enrichment.data)}
        </code>
      )}
    </div>
  );
}
