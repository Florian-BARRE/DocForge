// ====== Code Summary ======
// Polls one transfer's status until it reaches a terminal state (done/failed). Mirrors the
// monitoring feature's job-polling idiom (see features/monitoring/state/useJobDetail.ts) but kept
// local to this feature per the codebase's slice-isolation convention — transfers have no SSE
// stream, so this is a usePolling loop, armed only while a transfer id is set.

import { useState } from "react";
import { getTransfer, type TransferStatus } from "../../../api/transfers";
import { errorMessage } from "../../../hooks/errorMessage";
import { usePolling } from "../../../hooks/usePolling";

const POLL_MS = 1500;
const TERMINAL = new Set(["done", "failed"]);

export function useTransfer(transferId: string | null) {
  const [transfer, setTransfer] = useState<TransferStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A transient blip (network / 5xx) must NOT freeze a long export's progress — surface it but
  // keep polling (the default); the next tick recovers once the transfer resumes reporting.
  usePolling(
    () => getTransfer(transferId as string),
    {
      intervalMs: POLL_MS,
      enabled: transferId !== null,
      onReset: () => {
        if (!transferId) {
          setTransfer(null);
          setError(null);
        }
      },
      onData: (status) => { setTransfer(status); setError(null); },
      onError: (e) => setError(errorMessage(e)),
      isDone: (status) => TERMINAL.has(status.status),
    },
    [transferId],
  );

  return { transfer, error } as const;
}
