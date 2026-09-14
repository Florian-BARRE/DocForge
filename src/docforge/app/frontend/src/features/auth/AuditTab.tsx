// ====== Code Summary ======
// Settings ▸ Audit — a keyset-paginated read of the append-only audit trail (GET /api/v1/audit,
// root/full-access only). "Load more" appends the next page via `next_cursor`; a 403 here means the
// active key is collection-scoped (not a bug), surfaced as a plain permission message, not a retry.

import { useEffect, useState } from "react";
import { listAudit, type AuditEntry } from "../../api/audit";
import { HttpError } from "../../api/http";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme } from "../../theme";
import { AuditTable } from "./AuditTable";

const PAGE_SIZE = 50;

export function AuditTab() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const load = () => {
    setError(null);
    setForbidden(false);
    listAudit({ limit: PAGE_SIZE })
      .then((page) => {
        setEntries(page.entries);
        setCursor(page.next_cursor);
      })
      .catch((e) => {
        if (e instanceof HttpError && e.status === 403) setForbidden(true);
        else setError(e instanceof Error ? e.message : String(e));
      });
  };

  useEffect(load, []);

  const loadMore = () => {
    if (!cursor) return;
    setLoadingMore(true);
    listAudit({ limit: PAGE_SIZE, cursor })
      .then((page) => {
        setEntries((prev) => [...(prev ?? []), ...page.entries]);
        setCursor(page.next_cursor);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoadingMore(false));
  };

  if (forbidden)
    return (
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, padding: theme.space.xxl, textAlign: "center" }}>
        The audit trail is restricted to full-access keys — this key's scope can't read it.
      </div>
    );
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!entries) return <LoadingState label="loading audit trail…" />;
  if (entries.length === 0)
    return (
      <div
        style={{
          border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
          padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
        }}
      >
        No audit activity recorded yet.
      </div>
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <AuditTable entries={entries} />
      {cursor && (
        <div style={{ display: "flex", justifyContent: "center" }}>
          <Button variant="secondary" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? "loading…" : "Load more"}
          </Button>
        </div>
      )}
    </div>
  );
}
