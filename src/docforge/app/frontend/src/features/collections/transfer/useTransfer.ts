// ====== Code Summary ======
// Polls one transfer's status until it reaches a terminal state (done/failed). Mirrors the
// monitoring feature's job-polling idiom (see features/monitoring/state/useJobDetail.ts) but kept
// local to this feature per the codebase's slice-isolation convention — transfers have no SSE
// stream, so this is a plain setTimeout poll loop, armed only while a transfer id is set.

import { useEffect, useState } from "react";
import { getTransfer, type TransferStatus } from "../../../api/transfers";

const POLL_MS = 1500;
const TERMINAL = new Set(["done", "failed"]);

export function useTransfer(transferId: string | null) {
  const [transfer, setTransfer] = useState<TransferStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!transferId) {
      setTransfer(null);
      setError(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getTransfer(transferId)
        .then((status) => {
          if (cancelled) return;
          setTransfer(status);
          setError(null);
          if (!TERMINAL.has(status.status)) timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => {
          if (cancelled) return;
          // A transient blip (network / 5xx) must NOT freeze a long export's progress — surface it
          // but keep polling; the next tick recovers once the transfer resumes reporting.
          setError(e instanceof Error ? e.message : String(e));
          timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [transferId]);

  return { transfer, error } as const;
}
