// ====== Code Summary ======
// The "rates" half of the overrides editor — one editable row per model/provider actually seen in
// the last estimate run (or already overridden), grouped by the shape the backend prices against:
// chat (LLM/VLM, paired input+output) / embed (single rate) / OCR (single per-page rate, keyed by
// provider kind). Renders nothing per group with no targets — an untouched pipeline offers nothing
// to override yet.

import { theme } from "../../../theme";
import { withRate, type RatesDraft } from "./estimateOverridesDraft";
import { RateModelRow } from "./RateModelRow";
import type { RateTargets } from "./rateTargets";
import { RateSingleRateRow } from "./RateSingleRateRow";

interface EstimateRatesFormProps {
  targets: RateTargets;
  draft: RatesDraft;
  onChange: (next: RatesDraft) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: theme.font.size.xs, color: theme.color.mute, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: theme.space.xs }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>{children}</div>
    </div>
  );
}

export function EstimateRatesForm({ targets, draft, onChange }: EstimateRatesFormProps) {
  const hasAnyTarget = targets.chatModels.length + targets.embedModels.length + targets.ocrProviders.length > 0;
  if (!hasAnyTarget)
    return (
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        Run an estimate first — the priced models and providers it finds become editable here.
      </div>
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.l }}>
      {targets.chatModels.length > 0 && (
        <Section title="LLM / VLM models (USD per 1M tokens)">
          {targets.chatModels.map(({ key }) => (
            <RateModelRow
              key={key}
              modelId={key}
              value={draft.models[key] ?? {}}
              onChange={(value) => onChange({ ...draft, models: { ...draft.models, [key]: value } })}
            />
          ))}
        </Section>
      )}
      {targets.embedModels.length > 0 && (
        <Section title="Embedding models (USD per 1M tokens)">
          {targets.embedModels.map(({ key }) => (
            <RateSingleRateRow
              key={key}
              label={key}
              unit="$/1M"
              value={draft.embed[key]}
              onChange={(value) => onChange({ ...draft, embed: withRate(draft.embed, key, value) })}
            />
          ))}
        </Section>
      )}
      {targets.ocrProviders.length > 0 && (
        <Section title="OCR providers (USD per page)">
          {targets.ocrProviders.map(({ key }) => (
            <RateSingleRateRow
              key={key}
              label={key}
              unit="$/page"
              value={draft.ocr[key]}
              onChange={(value) => onChange({ ...draft, ocr: withRate(draft.ocr, key, value) })}
            />
          ))}
        </Section>
      )}
    </div>
  );
}
