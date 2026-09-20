// ====== Code Summary ======
// The collection-scoped trace-payload purge request/toast path — mirrors `useDeleteCollection`'s
// shape (own pending/error state, toasts the outcome, reports the result so the call site drives
// its own confirm UI). Shared by DangerZone's manual purge and TracePurgeOfferDialog's accept path.

import { useState } from "react";
import { purgeCollectionTracePayloads, type TracePurgeResult } from "../../../api/collections";
import { useToast } from "../../../shell/toast";

interface UseCollectionTracePurgeResult {
  pending: boolean;
  error: string | null;
  /** Purges the collection's stored heavy traces, toasts the outcome, and resolves the counts on
   *  success or `null` on failure. */
  purge: () => Promise<TracePurgeResult | null>;
}

export function useCollectionTracePurge(collectionId: string): UseCollectionTracePurgeResult {
  const toast = useToast();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const purge = async (): Promise<TracePurgeResult | null> => {
    setPending(true);
    setError(null);
    try {
      const result = await purgeCollectionTracePayloads(collectionId);
      toast.success(
        result.deleted_objects === 0
          ? "No stored traces to reclaim."
          : `Reclaimed ${result.deleted_objects} object(s) across ${result.purged_jobs} job(s).`,
      );
      return result;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      toast.error(`Trace purge failed — ${message}`);
      return null;
    } finally {
      setPending(false);
    }
  };

  return { pending, error, purge };
}
