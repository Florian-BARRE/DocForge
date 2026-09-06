// ====== Code Summary ======
// The query-understanding step of the search rail — an OFF-by-default, mutually-exclusive choice of
// one LLM query transform (rewrite | HyDE) spliced between normalize and encode (topology edit, see
// blobOps.setQueryTransform). Drawn like an ingestion stage: a segmented Off/Rewrite/HyDE selector
// in the frame, greyed when off; when on, its provider config (endpoint, model, key, temperature)
// is revealed inline. Forge orange marks the ONE active transform — "Off" reads as steel, not work.

import { useState } from "react";
import type { Palette } from "../../api/types";
import { NumberField } from "../../components/schema-form/NumberField";
import { findNodeCard } from "../../components/schema-form/paletteLookup";
import { SearchStageFrame } from "./SearchStageFrame";
import type { QueryTransformKind } from "./state/blobOps";
import { theme as t } from "../../theme";

// The DOM anchor for the rare fallback rendering (no `normalize` node to nest under, see
// SearchPipelineRail) — not wired into the minimap's own step list (that fallback path is a
// degraded custom-blob case, not one of the pipeline's 6 canonical steps), but still jump/track-able
// on its own via the shared `stageAnchorId` convention if ever needed.
const QUERY_FALLBACK_ANCHOR_KEY = "query-fallback";

// Last-resort fallback only — the real values come from the active method's own `config_schema`
// (`GET /pipelines/search`, already fetched as `palette` by the editor), so a backend default
// change (e.g. a new stock model) shows up here with zero frontend edit. This mirrors
// `QueryRewriteConfig`/`QueryHydeConfig` (both inherit `BaseQueryLlmConfig`) only as a safety net
// for the unexpected case where the schema is missing a field.
const FALLBACK_DEFAULTS = { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", temperature: 0 } as const;
const REDACTED_PREFIX = "__redacted__";

/** The active method's own schema default for one field, falling back when the schema lacks it. */
function schemaDefault<T>(palette: Palette, kind: QueryTransformKind | null, field: keyof typeof FALLBACK_DEFAULTS, guard: (v: unknown) => v is T): T {
  const card = kind ? findNodeCard(palette, "query", kind) : undefined;
  const raw = card?.config_schema.properties?.[field]?.default;
  return guard(raw) ? raw : (FALLBACK_DEFAULTS[field] as T);
}

const isString = (v: unknown): v is string => typeof v === "string";
const isNumber = (v: unknown): v is number => typeof v === "number";

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
  /** The search pipeline's palette — source of the active method's own config-schema defaults. */
  palette: Palette;
  onSelect: (kind: QueryTransformKind | null) => void;
  onChangeConfig: (field: string, value: unknown) => void;
  /** Folds this into step 1's own card body (a plain inset block, no second numbered frame) instead
   *  of rendering it as its own full SearchStageFrame — Query understanding is a modifier of the
   *  first step (normalize), not a numbered sibling step of its own. */
  nested?: boolean;
}

export function SearchQueryCard({ active, config, palette, onSelect, onChangeConfig, nested }: SearchQueryCardProps) {
  const [expanded, setExpanded] = useState(true);
  const enabled = active !== null;
  const defaultBaseUrl = schemaDefault(palette, active, "base_url", isString);
  const defaultModel = schemaDefault(palette, active, "model", isString);
  const defaultTemperature = schemaDefault(palette, active, "temperature", isNumber);

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
          value={String(config?.base_url ?? defaultBaseUrl)}
          onChange={(e) => onChangeConfig("base_url", e.target.value)}
        />
      </Field>
      <Field label="Model">
        <input
          style={inputStyle}
          value={String(config?.model ?? defaultModel)}
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
          value={typeof config?.temperature === "number" ? config.temperature : defaultTemperature}
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
      anchorKey={QUERY_FALLBACK_ANCHOR_KEY}
      collapsible={enabled}
      expanded={expanded}
      onToggleExpand={() => setExpanded((v) => !v)}
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
