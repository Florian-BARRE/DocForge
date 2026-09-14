// ====== Code Summary ======
// The expanded body of one trace node row: its input/output shape summaries (always available when
// trace capture ran) plus, only when the collection opted into full-payload capture, a lazy
// "Load input"/"Load output" button per slot (JobEventPayloadButton). Split out of JobEventItem so
// the row itself stays a thin single-responsibility summary line.

import type { JobEvent } from "../../api/jobs";
import { theme } from "../../theme";
import { JobEventPayloadButton } from "./JobEventPayloadButton";

// The shape summary's `hash` is a full content hash — truncate it for display, same convention as
// every other id/hash rendered short elsewhere in the app.
const HASH_DISPLAY_LENGTH = 16;

function formatSummaryValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (key === "hash" && typeof value === "string") {
    return value.length > HASH_DISPLAY_LENGTH ? `${value.slice(0, HASH_DISPLAY_LENGTH)}…` : value;
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function SummaryBlock({ label, summary }: { label: string; summary: Record<string, unknown> }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute, fontWeight: theme.font.weight.semibold }}>
        {label}
      </span>
      {Object.entries(summary).map(([key, value]) => (
        <span key={key} style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          {key}: <span style={{ color: theme.color.text }}>{formatSummaryValue(key, value)}</span>
        </span>
      ))}
    </div>
  );
}

interface JobEventDetailProps {
  jobId: string;
  event: JobEvent;
}

export function JobEventDetail({ jobId, event }: JobEventDetailProps) {
  const hasAnything = Boolean(
    event.input_summary || event.output_summary || event.has_full_input || event.has_full_output,
  );
  if (!hasAnything) {
    return (
      <div style={{ fontSize: theme.font.size.xs, color: theme.color.mute, padding: `${theme.space.xs}px 0 ${theme.space.s}px` }}>
        No captured input/output for this node.
      </div>
    );
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.xl, padding: `${theme.space.s}px 0 ${theme.space.m}px` }}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s, minWidth: 200 }}>
        {event.input_summary && <SummaryBlock label="input shape" summary={event.input_summary} />}
        {event.has_full_input && <JobEventPayloadButton jobId={jobId} eventId={event.event_id} slot="input" />}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s, minWidth: 200 }}>
        {event.output_summary && <SummaryBlock label="output shape" summary={event.output_summary} />}
        {event.has_full_output && <JobEventPayloadButton jobId={jobId} eventId={event.event_id} slot="output" />}
      </div>
    </div>
  );
}
