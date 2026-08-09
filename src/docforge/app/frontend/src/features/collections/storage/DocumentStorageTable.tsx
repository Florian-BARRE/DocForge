// ====== Code Summary ======
// The per-document storage table — sortable by any byte column (defaults to the server's own
// order: total descending). Client-side sort only; the backend already returns every document in
// one response, so no extra fetch is needed to re-sort.

import { useMemo, useState } from "react";
import type { DocumentStorageBreakdown } from "../../../api/collections";
import type { Navigate } from "../../../shell/view";
import { theme as t } from "../../../theme";
import { DocumentStorageRow } from "./DocumentStorageRow";
import { STORAGE_STORES, type StoreKey } from "./storageStores";

type SortKey = "filename" | "s3" | "postgres" | "qdrant" | "total";
type SortDirection = "asc" | "desc";

interface DocumentStorageTableProps {
  documents: DocumentStorageBreakdown[];
  collectionId: string;
  onNavigate: Navigate;
}

const STORE_COLOR: Record<StoreKey, string> = Object.fromEntries(STORAGE_STORES.map(({ key, color }) => [key, color])) as Record<StoreKey, string>;

const COLUMNS: { key: SortKey; label: string; align: "left" | "right"; storeKey?: StoreKey }[] = [
  { key: "filename", label: "Document", align: "left" },
  { key: "s3", label: "S3", align: "right", storeKey: "s3" },
  { key: "postgres", label: "PostgreSQL", align: "right", storeKey: "postgres" },
  { key: "qdrant", label: "Qdrant", align: "right", storeKey: "qdrant" },
  { key: "total", label: "Total", align: "right" },
];

function sortValue(document: DocumentStorageBreakdown, key: SortKey): string | number {
  switch (key) {
    case "filename": return document.filename.toLowerCase();
    case "s3": return document.s3.total_bytes;
    case "postgres": return document.postgres.total_bytes;
    case "qdrant": return document.qdrant.total_bytes;
    case "total": return document.total_bytes;
  }
}

export function DocumentStorageTable({ documents, collectionId, onNavigate }: DocumentStorageTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("total");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const sorted = useMemo(() => {
    const factor = sortDirection === "asc" ? 1 : -1;
    return [...documents].sort((a, b) => {
      const va = sortValue(a, sortKey);
      const vb = sortValue(b, sortKey);
      return va < vb ? -1 * factor : va > vb ? 1 * factor : 0;
    });
  }, [documents, sortKey, sortDirection]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  };

  if (documents.length === 0)
    return (
      <div style={{ border: `1px dashed ${t.color.lineStrong}`, borderRadius: t.radius.l, padding: t.space.xl, textAlign: "center", color: t.color.dim, fontSize: t.font.size.m }}>
        No documents ingested yet.
      </div>
    );

  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, overflow: "hidden" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
            {COLUMNS.map(({ key, label, align, storeKey }) => (
              <th
                key={key}
                onClick={() => toggleSort(key)}
                style={{
                  textAlign: align, color: t.color.dim, fontSize: t.font.size.xs,
                  padding: `${t.space.s}px ${t.space.m}px`, fontWeight: t.font.weight.semibold,
                  textTransform: "uppercase", letterSpacing: "0.04em", cursor: "pointer", userSelect: "none",
                }}
              >
                {storeKey && (
                  <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: t.radius.pill, background: STORE_COLOR[storeKey], marginRight: t.space.xs }} />
                )}
                {label}{sortKey === key && (sortDirection === "asc" ? " ▲" : " ▼")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((document) => (
            <DocumentStorageRow key={document.document_id} document={document} collectionId={collectionId} onNavigate={onNavigate} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
