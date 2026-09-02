// ====== Code Summary ======
// The humanization layer for every schema-driven form (`SchemaForm`/`SchemaField`): turns a raw
// backend wire name (`job_timeout_seconds`, `do_ocr`) into a human label, and — for the handful of
// fields whose backend `description` leaks an internal name (an env var, "stored blob", a Python
// type) — a rewritten, jargon-free help sentence. Unknown fields still get a readable label via
// `autoHumanizeLabel`'s snake_case → Title Case fallback, so a brand-new backend field is never
// worse than today, even before anyone adds it here. Purely additive: nothing here can change what
// gets submitted, only how the control reads.

/** A human label + a jargon-free help sentence for one wire field name. Both optional — a field can
 *  override just the label (keep the backend's own description) or just the help text. */
interface FieldCopy {
  label?: string;
  help?: string;
}

// Seeded with the collection contract's own fields (the wizard's Identity step) plus the handful of
// cross-cutting config knobs every provider node shares via `TimeoutConfig`/`TimeoutRetryConfig`
// (see shared_libs/public_models/base.py) — the fields a user meets across nearly every stage-rail
// config card. Intentionally partial, not exhaustive: every other field still reads fine through
// the auto-humanized fallback below.
const FIELD_COPY: Record<string, FieldCopy> = {
  // Collection contract (StepIdentity).
  name: { label: "Collection name" },
  supported_formats: {
    label: "Accepted file formats",
    help: "Only files in these formats can be uploaded to this collection.",
  },
  max_file_size_bytes: { label: "Max file size" },
  job_timeout_seconds: {
    label: "Job timeout",
    help: "How long one ingest job may run before it's stopped. Leave unset to use the server default.",
  },
  preset: {
    label: "Starting pipeline",
    help: "A ready-made ingestion recipe, fully customizable afterwards from the Pipeline tab. Both "
      + "options run entirely on local, free in-stack services out of the box — no paid API calls "
      + "until you explicitly opt a provider-hosted stage in.",
  },

  // Shared timeout/retry mixin — present on almost every provider-hosted node config.
  timeout_seconds: { label: "Request timeout", help: "How long to wait for one provider call before giving up." },
  preflight_timeout_seconds: {
    label: "Reachability check timeout",
    help: "How long the health check waits for this provider to respond before flagging it unreachable.",
  },
  max_retries: { label: "Max retries", help: "How many times to retry a failed call before giving up." },
  retry_backoff_seconds: { label: "Retry delay", help: "How long to wait between retries." },

  // Other very common provider knobs.
  base_url: { label: "Endpoint URL" },
  api_key: { label: "API key" },
  model: { label: "Model" },
  temperature: { label: "Temperature", help: "Higher values make the output more varied; lower values more deterministic." },
  batch_size: { label: "Batch size", help: "How many items are sent to the provider in one call." },
  enabled: { label: "Enabled" },
  do_ocr: { label: "Run OCR", help: "Extract text from scanned pages and images." },
  do_table_structure: { label: "Detect table structure", help: "Recognize table rows/columns instead of reading them as plain text." },
};

/** snake_case → "Title Case" — the fallback for any field not curated in `FIELD_COPY` above. */
function autoHumanizeLabel(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

// A unit is MEANING, not a technical detail — it must render as a visible field adornment, never
// hidden behind "Show technical details". Derived from the backend's own unit-suffixed field
// naming convention (`*_seconds`, `*_bytes`…), so a brand-new timeout/size field gets its unit for
// free, with zero edits here.
const UNIT_SUFFIX_PATTERNS: [RegExp, string][] = [
  [/_seconds$/, "seconds"],
  [/_ms$/, "ms"],
  [/_bytes$/, "bytes"],
  [/_mb$/, "MB"],
  [/_percent$/, "%"],
];

/** The unit adornment a numeric field's control should show next to its input, derived from the
 *  wire field name's own unit suffix — `undefined` for unitless numbers (counts, ratios, scores). */
export function humanizeFieldUnit(name: string): string | undefined {
  return UNIT_SUFFIX_PATTERNS.find(([pattern]) => pattern.test(name))?.[1];
}

/** The label a `SchemaField` should render for a wire field name. */
export function humanizeFieldLabel(name: string): string {
  return FIELD_COPY[name]?.label ?? autoHumanizeLabel(name);
}

/** The help sentence a `SchemaField` should render — the curated rewrite when one exists, otherwise
 *  the backend's own `description` verbatim (falls through to `undefined` when neither exists). */
export function humanizeFieldHelp(name: string, backendDescription?: string): string | undefined {
  return FIELD_COPY[name]?.help ?? backendDescription;
}

/** snake_case enum member → "Title Case" display text — the wire `value` never changes, only the
 *  rendered `<option>` label, so a raw backend literal (`digital_born`, `keyword_list`) never
 *  reaches the user verbatim. */
export function humanizeEnumOption(value: string): string {
  return autoHumanizeLabel(value);
}
