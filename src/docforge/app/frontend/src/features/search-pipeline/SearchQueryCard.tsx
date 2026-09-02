// ====== Code Summary ======
// The query-understanding step of the search rail — an OFF-by-default, mutually-exclusive choice of
// one LLM query transform (rewrite | HyDE) spliced between normalize and encode (topology edit, see
// blobOps.setQueryTransform). Drawn like an ingestion stage: a segmented Off/Rewrite/HyDE selector
// in the frame, greyed when off; when on, its provider config (endpoint, model, key, temperature)
// is revealed inline. Forge orange marks the ONE active transform — "Off" reads as steel, not work.

import { NumberField } from "../../components/schema-form/NumberField";
import { SearchStageFrame } from "./SearchStageFrame";
import type { QueryTransformKind } from "./state/blobOps";
import { theme as t } from "../../theme";

// Display-only fallbacks for the provider fields: a freshly-spliced node carries an EMPTY config,
// and the backend applies these same endpoint defaults from `{}` — so the card shows the effective
// value without writing it (leaving it unwritten lets the collection track backend default changes).
const CONFIG_DEFAULTS = { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", temperature: 0 } as const;
const REDACTED_PREFIX = "__redacted__";

interface Option {
  value: QueryTransformKind | null;
  label: string;
}
const OPTIONS: Option[] = [
  { value: null, label: "Off" },
  { value: "rewrite", label: "Rewrite" },
  { value: "hyde", label: "HyDE" },
];

// Per-mode summary — the card's one-line explanation should say what's actually about to happen,
// not a generic blurb that doesn't distinguish "off" from either transform.
const SUMMARY_BY_MODE: Record<"off" | QueryTransformKind, string> = {
  off: "The raw query goes straight to retrieval — no extra LLM call, no added latency or cost.",
  rewrite: "An LLM rewrites/expands the query before retrieval; adds a paid call per search, degrades to the raw query on any error.",
  hyde: "An LLM drafts a hypothetical answer and embeds THAT instead of the raw query (HyDE); adds a paid call per search, degrades to the raw query on any error.",
};

const inputStyle: React.CSSProperties = {
  background: t.color.surface2,
  color: t.color.text,
  border: `1px solid ${t.color.lineStrong}`,
  borderRadius: t.radius.m,
  padding: "6px 8px",
  fontSize: t.font.size.m,
  fontFamily: t.font.mono, // endpoint / model id / key / temperature are all machine values
  width: "100%",
};

interface SearchQueryCardProps {
  active: QueryTransformKind | null;
  /** The active transform node's config (its provider knobs); null when off. */
  config: Record<string, unknown> | null;
  onSelect: (kind: QueryTransformKind | null) => void;
  onChangeConfig: (field: string, value: unknown) => void;
  /** Folds this into step 1's own card body (a plain inset block, no second numbered frame) instead
   *  of rendering it as its own full SearchStageFrame — Query understanding is a modifier of the
   *  first step (normalize), not a numbered sibling step of its own. */
  nested?: boolean;
}

export function SearchQueryCard({ active, config, onSelect, onChangeConfig, nested }: SearchQueryCardProps) {
  const enabled = active !== null;

  const selector = (
    <div
      role="radiogroup"
      aria-label="Query understanding"
      style={{
        display: "inline-flex", alignItems: "stretch", gap: 2, padding: 2,
        background: t.color.surface2, border: `1px solid ${t.color.lineStrong}`, borderRadius: t.radius.pill,
      }}
    >
      {OPTIONS.map((option) => {
        const selected = active === option.value;
        const isWork = selected && option.value !== null; // orange only for the ONE active transform
        return (
          <button
            key={option.label}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onSelect(option.value)}
            style={{
              cursor: "pointer", border: "none",
              borderRadius: t.radius.pill, padding: "4px 12px",
              fontFamily: t.font.family, fontSize: t.font.size.s, fontWeight: 600,
              background: isWork ? t.color.accent : selected ? t.color.surface3 : "transparent",
              color: isWork ? t.color.onAccent : selected ? t.color.text : t.color.dim,
              transition: "background .15s ease, color .15s ease",
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );

  const rawKey = String(config?.api_key ?? "");
  const keyRedacted = rawKey.startsWith(REDACTED_PREFIX);

  const fields = enabled && (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "10px 10px" }}>
      <Field label="Endpoint URL">
        <input
          style={inputStyle}
          value={String(config?.base_url ?? CONFIG_DEFAULTS.base_url)}
          onChange={(e) => onChangeConfig("base_url", e.target.value)}
        />
      </Field>
      <Field label="Model">
        <input
          style={inputStyle}
          value={String(config?.model ?? CONFIG_DEFAULTS.model)}
          onChange={(e) => onChangeConfig("model", e.target.value)}
        />
      </Field>
      <Field label="API key">
        {/* A stored key is masked on read (`__redacted__<last4>`) — show it as the placeholder and
            keep the field blank so leaving it untouched restores the real key server-side; typing
            overwrites it. */}
        <input
          type="password"
          style={inputStyle}
          value={keyRedacted ? "" : rawKey}
          placeholder={keyRedacted ? rawKey : "sk-…"}
          onChange={(e) => onChangeConfig("api_key", e.target.value)}
        />
      </Field>
      <Field label="Temperature">
        <NumberField
          value={typeof config?.temperature === "number" ? (config.temperature as number) : CONFIG_DEFAULTS.temperature}
          min={0}
          style={inputStyle}
          onChange={(value) => onChangeConfig("temperature", value)}
        />
      </Field>
    </div>
  );

  if (nested) {
    return (
      <div
        style={{
          marginTop: t.space.m, paddingTop: t.space.m, borderTop: `1px dashed ${t.color.line}`,
          display: "flex", flexDirection: "column", gap: t.space.s,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
          <span style={{ fontFamily: t.font.family, fontSize: t.font.size.s, fontWeight: 600, color: t.color.text }}>
            Query understanding
          </span>
          {selector}
        </div>
        <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>{SUMMARY_BY_MODE[active ?? "off"]}</div>
        {fields}
      </div>
    );
  }

  return (
    <SearchStageFrame
      left={selector}
      title="Query understanding"
      tag="query"
      summary={SUMMARY_BY_MODE[active ?? "off"]}
      enabled={enabled}
    >
      {fields}
    </SearchStageFrame>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: t.font.size.s }}>
      <span style={{ color: t.color.text }}>{label}</span>
      {children}
    </div>
  );
}
