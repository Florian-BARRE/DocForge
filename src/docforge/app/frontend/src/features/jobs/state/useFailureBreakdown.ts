// ====== Code Summary ======
// Polls `GET /jobs/failures/breakdown` (fleet-wide, default window) for the breakdown panel.

import { useState } from "react";
import { getFailureBreakdown, type FailureBreakdown } from "../../../api/jobs";
import { errorMessage } from "../../../hooks/errorMessage";
import { usePolling } from "../../../hooks/usePolling";

const POLL_MS = 30000;

export function useFailureBreakdown(windowHours: number): { data: FailureBreakdown | null; error: string | null } {
  const [data, setData] = useState<FailureBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePolling(
    () => getFailureBreakdown({ windowHours }),
    {
      intervalMs: POLL_MS,
      onReset: () => setData(null),
      onData: (next) => { setData(next); setError(null); },
      onError: (e) => setError(errorMessage(e)),
    },
    [windowHours],
  );

  return { data, error };
}
