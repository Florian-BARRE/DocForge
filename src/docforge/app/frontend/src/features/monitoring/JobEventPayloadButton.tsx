// ====== Code Summary ======
// One trace node's lazy "Load input"/"Load output" affordance for a single slot — fetches the FULL
// raw payload on click (never automatically; a captured IR can be heavy) and delegates its rendering
// to `TracePayloadView` (clickable blob references, readable text, raw-JSON toggle). Owns its own
// loading/error/truncated/no-full-payload states so JobEventDetail stays a thin layout shell.

import { useState } from "react";
import { HttpError } from "../../api/http";
import { getEventPayload, type JobEventPayload, type JobEventPayloadSlot } from "../../api/jobs";
import { Button } from "../../components/Button";
import { theme } from "../../theme";
import { TracePayloadView } from "./TracePayloadView";

type LoadState = "idle" | "loading" | "error" | "empty";

interface JobEventPayloadButtonProps {
  jobId: string;
  eventId: string;
  slot: JobEventPayloadSlot;
}

export function JobEventPayloadButton({ jobId, eventId, slot }: JobEventPayloadButtonProps) {
  const [state, setState] = useState<LoadState>("idle");
  const [payload, setPayload] = useState<JobEventPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const result = await getEventPayload(jobId, eventId, slot);
      setPayload(result);
      setState("idle");
    } catch (err) {
      // A 404 here means the row only ever carried a shape summary (or the payload aged out) —
      // a defensive fallback, since `has_full_*` should already have gated this button off.
      if (err instanceof HttpError && err.status === 404) {
        setState("empty");
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load payload.");
      setState("error");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, alignItems: "flex-start" }}>
      {!payload && (
        <Button size="sm" variant="secondary" onClick={load} disabled={state === "loading"}>
          {state === "loading" ? "Loading…" : `Load ${slot}`}
        </Button>
      )}
      {state === "error" && <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{error}</span>}
      {state === "empty" && (
        <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>no full payload captured</span>
      )}
      {payload?.truncated && (
        <span style={{ color: theme.color.warnStrong, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}>
          payload too large — {payload.size_bytes.toLocaleString()} bytes
        </span>
      )}
      {payload && !payload.truncated && <TracePayloadView payload={payload.payload} />}
    </div>
  );
}
