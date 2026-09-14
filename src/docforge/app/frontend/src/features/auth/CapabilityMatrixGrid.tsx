// ====== Code Summary ======
// The "what can this deployment do NOW" grid — one row per pipeline family, its available kinds as
// quiet chips. Family order mirrors CapabilityMatrix's own field order (parse-time provider
// families first, then generic capabilities), not alphabetical.

import { Fragment } from "react";
import type { CapabilityMatrix } from "../../api/capabilities";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";

const FAMILY_LABELS: { key: keyof CapabilityMatrix; label: string }[] = [
  { key: "parsers", label: "Parsers" },
  { key: "ocr", label: "OCR" },
  { key: "embed", label: "Embed" },
  { key: "chunkers", label: "Chunkers" },
  { key: "vlm", label: "VLM" },
  { key: "llm", label: "LLM" },
  { key: "rerank", label: "Rerank" },
  { key: "contextualize", label: "Contextualize" },
  { key: "metagen", label: "Metagen" },
];

export function CapabilityMatrixGrid({ capabilities }: { capabilities: CapabilityMatrix }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "140px 1fr", rowGap: t.space.s, columnGap: t.space.m }}>
      {FAMILY_LABELS.map(({ key, label }) => {
        const kinds = capabilities[key];
        return (
          <Fragment key={key}>
            <span style={{ color: t.color.dim, fontSize: t.font.size.s, paddingTop: 2 }}>{label}</span>
            <div style={{ display: "flex", gap: t.space.xs, flexWrap: "wrap" }}>
              {kinds.length === 0 ? (
                <span style={{ color: t.color.mute, fontSize: t.font.size.s }}>none configured</span>
              ) : (
                kinds.map((kind) => <Chip key={kind} tone="capability">{kind}</Chip>)
              )}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
