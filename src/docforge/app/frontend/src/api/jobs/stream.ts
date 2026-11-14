// ====== Code Summary ======
// Live job event stream: `fetch`-based SSE consumer (the native EventSource cannot send the
// Authorization header) that parses `data: {json}` frames off the ReadableStream.

import { clearApiToken, getApiToken, HttpError } from "../http";
import { JOBS_BASE as BASE } from "./base";
import type { JobEvent, JobStatus } from "./types";

/** Callbacks the live job stream drives — one per new stage event, one per status snapshot change. */
export interface JobStreamHandlers {
  onEvent: (event: JobEvent) => void;
  onStatus: (status: JobStatus) => void;
  signal?: AbortSignal;
}

/**
 * Consume a job's live SSE feed (`GET /jobs/{id}/stream`) until it closes at terminal state.
 *
 * The API is header-only auth (Authorization: Bearer), which the native EventSource cannot set — so
 * we open the stream with `fetch` (which CAN carry the header) and parse the `data: {json}\n\n`
 * frames off the ReadableStream ourselves. Each frame carries a `frame` type — `"event"` (a stage
 * event) or `"status"` (a JobStatus snapshot, which carries its own job `kind`). Resolves when the
 * server closes the stream (job terminal),
 * rejects on a non-2xx open or a transport error so callers can fall back to polling.
 */
export async function streamJobEvents(jobId: string, handlers: JobStreamHandlers): Promise<void> {
  const token = getApiToken();
  const response = await fetch(`${BASE}/${jobId}/stream`, {
    headers: {
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: handlers.signal,
  });
  if (!response.ok || !response.body) {
    if (response.status === 401) clearApiToken();
    throw new HttpError(response.status, [{ message: `Stream failed (${response.status})` }]);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line. Drain every complete frame in the buffer.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const rawFrame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const dataLine = rawFrame.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const payload = dataLine.slice(dataLine.indexOf(":") + 1).trim();
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(payload);
      } catch {
        continue; // partial/garbled frame — skip it, never crash the stream
      }
      if (frame.frame === "event") handlers.onEvent(frame as unknown as JobEvent);
      else if (frame.frame === "status") handlers.onStatus(frame as unknown as JobStatus);
    }
  }
}
