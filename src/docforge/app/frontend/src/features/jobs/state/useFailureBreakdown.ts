// ====== Code Summary ======
// Polls `GET /jobs/failures/breakdown` (fleet-wide, default window) for the breakdown panel.

import { useEffect, useState } from "react";
import { getFailureBreakdown, type FailureBreakdown } from "../../../api/jobs";

const POLL_MS = 30000;

export function useFailureBreakdown(windowHours: number): { data: FailureBreakdown | null; error: string | null } {
  const [data, setData] = useState<FailureBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    setData(null);

    const load = () => {
      getFailureBreakdown({ windowHours })
        .then((next) => {
          if (cancelled) return;
          setData(next);
          setError(null);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => {
          if (cancelled) return;
          setError(e instanceof Error ? e.message : String(e));
          timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [windowHours]);

  return { data, error };
}
