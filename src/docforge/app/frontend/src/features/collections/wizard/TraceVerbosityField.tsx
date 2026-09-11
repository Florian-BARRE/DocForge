// ====== Code Summary ======
// Dedicated first-class control for the collection contract's `trace_verbosity` field — pulled out
// of the generic schema-driven form (see StepIdentity's `delete properties.trace_verbosity`) so the
// choice is visible without expanding "Show technical details", the same treatment as the
// `job_timeout_seconds` control already gets. Built on the shared `SegmentedControl` primitive (the
// same "structural choice, not a buried dropdown" control the enrich-mode panel already uses). The
// enum choices and default all come from the backend's own contract schema property (`prop`) —
// nothing here hardcodes a literal that mirrors a backend default.

import type { JsonSchemaProperty } from "../../../api/types";
import { SegmentedControl, type SegmentedOption } from "../../../components/SegmentedControl";

const OPTION_COPY: Record<string, { label: string; description: string }> = {
  shape: {
    label: "Summary",
    description: "Default — keeps only a lightweight per-node input/output summary.",
  },
  full: {
    label: "Full",
    description: "Stores each node's full raw input/output for deep debugging — more storage, opt-in.",
  },
};

interface TraceVerbosityFieldProps {
  /** Undefined = not yet set on the draft — resolves to the schema's own `prop.default`. */
  value: string | undefined;
  onChange: (value: string) => void;
  /** The contract schema's own `trace_verbosity` property — supplies the enum choices and default
   *  straight from the backend (`GET /collections/contract-schema`). */
  prop: JsonSchemaProperty;
}

export function TraceVerbosityField({ value, onChange, prop }: TraceVerbosityFieldProps) {
  const choices = prop.enum ?? [];
  const defaultValue = typeof prop.default === "string" ? prop.default : choices[0];
  const current = value ?? defaultValue ?? "";

  const options: SegmentedOption<string>[] = choices.map((option) => ({
    value: option,
    label: OPTION_COPY[option]?.label ?? option,
    description: OPTION_COPY[option]?.description,
  }));

  return <SegmentedControl legend="Execution trace" value={current} options={options} onChange={onChange} />;
}
