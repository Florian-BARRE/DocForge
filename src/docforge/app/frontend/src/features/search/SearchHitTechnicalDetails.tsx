// ====== Code Summary ======
// The hit's machine-facing provenance (full document id, chunk index, token count) — demoted behind
// the shared collapsed-by-default AdvancedDisclosure so a business reader sees the human citation
// (SearchHitCitation) first and only an engineer opens this to debug a retrieval result. Reuses the
// SAME disclosure primitive as the rest of the app's "technical details" gates (search-pipeline node
// rail, storage breakdown) rather than inventing a new motif.

import type { SearchHitModel } from "../../api/search";
import { AdvancedDisclosure } from "../search-pipeline/AdvancedDisclosure";
import { theme } from "../../theme";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m }}>
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{label}</span>
      <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.text }}>{value}</span>
    </div>
  );
}

export function SearchHitTechnicalDetails({ hit }: { hit: SearchHitModel }) {
  return (
    <AdvancedDisclosure summary="Technical details">
      <Row label="Document id" value={hit.document_id} />
      <Row label="Chunk" value={`#${hit.chunk_index}`} />
      <Row label="Tokens" value={String(hit.token_count)} />
    </AdvancedDisclosure>
  );
}
