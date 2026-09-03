// ====== Code Summary ======
// The vision-model connection — endpoint, key, model, sampling, and the network timeouts/retries —
// tucked behind a collapsible disclosure so it never dominates the panel. Only rendered for the VLM
// backends (the local classifier needs no endpoint). Plain labelled inputs over the same flat config
// fields, edited through the rail's per-field onChange.

import { useState } from "react";

import { theme } from "../../../theme";
import { LabeledInput } from "./LabeledInput";
import { readNum, readStr } from "./enrichClassifyModel";

interface ClassifyVlmAdvancedProps {
  config: Record<string, unknown>;
  onChange: (field: string, value: unknown) => void;
}

export function ClassifyVlmAdvanced({ config, onChange }: ClassifyVlmAdvancedProps) {
  const [open, setOpen] = useState(false);
  const numberChange = (field: string, min?: number) => (v: string) => {
    const n = Number(v);
    if (Number.isFinite(n) && (min === undefined || n >= min)) onChange(field, n);
  };

  return (
    <div style={{ borderTop: `1px solid ${theme.color.line}`, paddingTop: theme.space.s }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{
          background: "transparent", border: "none", cursor: "pointer", padding: 0,
          fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold, color: theme.color.dim,
          display: "flex", alignItems: "center", gap: theme.space.xs,
        }}
      >
        <span aria-hidden style={{ fontFamily: theme.font.mono }}>{open ? "▾" : "▸"}</span>
        Vision model connection
      </button>
      {open && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.m, marginTop: theme.space.s }}>
          <LabeledInput label="Endpoint URL" help="OpenAI-compatible vision endpoint (e.g. a local vLLM)." mono
            value={readStr(config.base_url)} placeholder="http://localhost:8000/v1" onChange={(v) => onChange("base_url", v)} />
          <LabeledInput label="API key" help="May be empty for a local endpoint." mono
            value={readStr(config.api_key)} onChange={(v) => onChange("api_key", v)} />
          <LabeledInput label="Model" help="Vision model name served at the endpoint." mono
            value={readStr(config.model)} placeholder="qwen2.5-vl" onChange={(v) => onChange("model", v)} />
          <LabeledInput label="Temperature" type="number" min={0} max={2} step={0.1} mono
            help="Sampling temperature (0 = deterministic)."
            value={readNum(config.temperature, 0)} onChange={numberChange("temperature", 0)} />
          <LabeledInput label="Request timeout" type="number" min={1} suffix="s" mono
            help="How long to wait for one call before giving up."
            value={readNum(config.timeout_seconds, 30)} onChange={numberChange("timeout_seconds", 1)} />
          <LabeledInput label="Reachability timeout" type="number" min={1} suffix="s" mono
            help="How long the health check waits before flagging the endpoint unreachable."
            value={readNum(config.preflight_timeout_seconds, 10)} onChange={numberChange("preflight_timeout_seconds", 1)} />
          <LabeledInput label="Max retries" type="number" min={0} mono
            help="Retries of a failed call before giving up."
            value={readNum(config.max_retries, 2)} onChange={numberChange("max_retries", 0)} />
          <LabeledInput label="Retry delay" type="number" min={0} suffix="s" mono
            help="Wait between retries."
            value={readNum(config.retry_backoff_seconds, 1)} onChange={numberChange("retry_backoff_seconds", 0)} />
        </div>
      )}
    </div>
  );
}
