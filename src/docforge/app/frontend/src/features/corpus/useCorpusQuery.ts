// ====== Code Summary ======
// Server-driven fetch of one grid page — refetches whenever the collection, filter, sort or
// pagination window changes. `filter`/`sort` are expected to be memoized by the caller (CorpusPage
// derives them from state) so an unrelated re-render doesn't spuriously refetch. Also self-polls
// every `POLL_MS` while any row on the current page is still pending/processing — mirrors
// `JobsPage`'s idiom, so an active ingest job's status advances live in the grid too, not just
// on the Jobs tab.

import { useCallback, useEffect, useState } from "react";
import { queryDocuments, type DocumentFilter, type DocumentGridRow, type DocumentSort } from "../../api/corpus";

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

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = (isPoll: boolean) => {
      if (!isPoll) setLoading(true);
      setError(null);
      queryDocuments(collectionId, { filter, sort, pagination: { limit, offset } })
        .then((response) => {
          if (cancelled) return;
          setRows(response.rows);
          setTotal(response.total);
          if (response.rows.some(isActive)) timer = window.setTimeout(() => load(true), POLL_MS);
        })
        .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    load(false);

    return () => { cancelled = true; window.clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId, filter, sort, limit, offset, tick]);

  const patchRow = useCallback((id: string, patch: Partial<DocumentGridRow>) => {
    setRows((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }, []);

  return { rows, total, loading, error, refetch: () => setTick((t) => t + 1), patchRow };
}
