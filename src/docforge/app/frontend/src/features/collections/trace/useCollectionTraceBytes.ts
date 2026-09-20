// ====== Code Summary ======
// Fetches just the collection's current heavy-trace footprint (`trace_bytes`) via the storage
// accounting sweep — there is no dedicated lighter endpoint, so this reuses the same read the
// Overview's StorageFootprintPanel makes, self-contained (own fetch, own loading state), exactly
// like that panel already self-fetches independently of the rest of its page. Shared by DangerZone
// (gates/labels the manual purge action) and TracePurgeOfferDialog (labels the offer-on-disable dialog).

import { useEffect, useState } from "react";
import { fetchCollectionStorage } from "../../../api/collections";

interface UseCollectionTraceBytesResult {
  /** `null` while loading or on a failed fetch — callers should treat that as "unknown", not "zero". */
  traceBytes: number | null;
  loading: boolean;
}

export function useCollectionTraceBytes(collectionId: string): UseCollectionTraceBytesResult {
  const [traceBytes, setTraceBytes] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchCollectionStorage(collectionId)
      .then((storage) => {
        if (!cancelled) setTraceBytes(storage.trace_bytes);
      })
      .catch(() => {
        if (!cancelled) setTraceBytes(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [collectionId]);

  return { traceBytes, loading };
}
