// ====== Code Summary ======
// The document-scoped trace-payload purge request/toast path — the explorer-feature analogue of
// `features/collections/trace/useCollectionTracePurge`, kept as its own feature-local copy (small,
// domain-specific hooks are duplicated per feature in this codebase rather than shared cross-feature
// — see BulkConfirmDialog's own note on the same convention).

import { useState } from "react";
import { purgeDocumentTracePayloads } from "../../../api/documents";
import type { TracePurgeResult } from "../../../api/collections";
import { useToast } from "../../../shell/toast";

interface UseDocumentTracePurgeResult {
  pending: boolean;
  error: string | null;
  /** Purges the document's stored heavy traces, toasts the outcome, and resolves the counts on
   *  success or `null` on failure. */
  purge: () => Promise<TracePurgeResult | null>;
}

export function useDocumentTracePurge(documentId: string): UseDocumentTracePurgeResult {
  const toast = useToast();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const purge = async (): Promise<TracePurgeResult | null> => {
    setPending(true);
    setError(null);
    try {
      const result = await purgeDocumentTracePayloads(documentId);
      toast.success(
        result.deleted_objects === 0
          ? "No stored traces to reclaim for this document."
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
