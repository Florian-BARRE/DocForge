// ====== Code Summary ======
// Server-driven fetch of one grid page — refetches whenever the collection, filter, sort or
// pagination window changes. `filter`/`sort` are expected to be memoized by the caller (CorpusPage
// derives them from state) so an unrelated re-render doesn't spuriously refetch. Also self-polls
// every `POLL_MS` while any row on the current page is still pending/processing — mirrors
// the Activity tab's idiom, so an active ingest job's status advances live in the grid too, not
// just on the Jobs tab.

import { useCallback, useState } from "react";
import { queryDocuments, type DocumentFilter, type DocumentGridRow, type DocumentSort } from "../../api/corpus";
import { errorMessage } from "../../hooks/errorMessage";
import { usePolling } from "../../hooks/usePolling";

const POLL_MS = 2500;

interface UseCorpusQueryArgs {
  collectionId: string;
  filter: DocumentFilter;
  sort: DocumentSort | null;
  limit: number;
  offset: number;
}

export interface UseCorpusQueryResult {
  rows: DocumentGridRow[];
  total: number;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  /** Optimistic single-row patch (e.g. the enabled toggle's confirmed server state) — avoids a
   *  full refetch flash for a change that's already known. */
  patchRow: (id: string, patch: Partial<DocumentGridRow>) => void;
}

function isActive(row: DocumentGridRow): boolean {
  return row.status === "pending" || row.status === "processing";
}

export function useCorpusQuery({ collectionId, filter, sort, limit, offset }: UseCorpusQueryArgs): UseCorpusQueryResult {
  const [rows, setRows] = useState<DocumentGridRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Stops on the first error (`retryOnError: false`): the grid shows the error and `refetch` retries.
  usePolling(
    () => queryDocuments(collectionId, { filter, sort, pagination: { limit, offset } }),
    {
      intervalMs: POLL_MS,
      retryOnError: false,
      onFetchStart: (isPoll) => {
        if (!isPoll) setLoading(true);
        setError(null);
      },
      onData: (response) => { setRows(response.rows); setTotal(response.total); },
      onError: (e) => setError(errorMessage(e)),
      isDone: (response) => !response.rows.some(isActive),
      onSettled: () => setLoading(false),
    },
    [collectionId, filter, sort, limit, offset, tick],
  );

  const patchRow = useCallback((id: string, patch: Partial<DocumentGridRow>) => {
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }, []);

  // Stable identity (not a fresh closure per render) — CorpusPage's grid-columns memo depends on
  // it, and an unstable `refetch` would defeat that memoization on every unrelated state update
  // (e.g. the loading flag flipping mid-fetch).
  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { rows, total, loading, error, refetch, patchRow };
}
