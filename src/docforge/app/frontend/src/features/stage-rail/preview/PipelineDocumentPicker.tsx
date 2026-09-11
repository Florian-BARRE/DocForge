// ====== Code Summary ======
// A compact, debounced search-and-pick list of the collection's own documents — the "existing
// document" preview source. Reuses the corpus grid's own query endpoint (api/corpus.ts) at a small
// page size instead of a dedicated endpoint; this is a picker, not a grid, so no sort/pagination UI.

import { useEffect, useState } from "react";
import { queryDocuments, type DocumentGridRow } from "../../../api/corpus";
import { theme as t } from "../../../theme";

const DEBOUNCE_MS = 300;
const PAGE_LIMIT = 8;

interface PipelineDocumentPickerProps {
  collectionId: string;
  selectedId: string | null;
  onSelect: (doc: DocumentGridRow) => void;
}

export function PipelineDocumentPicker({ collectionId, selectedId, onSelect }: PipelineDocumentPickerProps) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<DocumentGridRow[]>([]);
  const [loading, setLoading] = useState(true);

  // Debounced search — re-queries the collection's documents on every keystroke settle.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const handle = window.setTimeout(() => {
      queryDocuments(collectionId, {
        filter: query.trim() ? { filename: { contains: query.trim() } } : undefined,
        sort: { field: "created_at", direction: "desc" },
        pagination: { limit: PAGE_LIMIT, offset: 0 },
      })
        .then((res) => { if (!cancelled) setRows(res.rows); })
        .catch(() => { if (!cancelled) setRows([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, DEBOUNCE_MS);
    return () => { cancelled = true; window.clearTimeout(handle); };
  }, [collectionId, query]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.xs }}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a document by filename…"
        style={{
          padding: `${t.space.s}px ${t.space.m}px`, borderRadius: t.radius.m,
          border: `1px solid ${t.color.line}`, background: t.color.surface,
          color: t.color.text, fontSize: t.font.size.m,
        }}
      />
      <div style={{ display: "flex", flexDirection: "column", gap: 2, maxHeight: 180, overflowY: "auto" }}>
        {loading && <div style={{ color: t.color.dim, fontSize: t.font.size.s, padding: t.space.s }}>searching…</div>}
        {!loading && rows.length === 0 && (
          <div style={{ color: t.color.dim, fontSize: t.font.size.s, padding: t.space.s }}>No document matches.</div>
        )}
        {!loading && rows.map((row) => {
          const active = row.id === selectedId;
          return (
            <button
              key={row.id}
              type="button"
              onClick={() => onSelect(row)}
              style={{
                textAlign: "left", cursor: "pointer", display: "flex", flexDirection: "column", gap: 1,
                padding: `${t.space.xs}px ${t.space.s}px`, borderRadius: t.radius.s,
                border: `1px solid ${active ? t.color.accentLine : "transparent"}`,
                background: active ? t.color.accentSoft : "transparent",
                color: active ? t.color.accentSafe : t.color.text,
              }}
            >
              <span
                style={{
                  fontSize: t.font.size.s, fontWeight: t.font.weight.semibold,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}
              >
                {row.title || row.filename}
              </span>
              <span style={{ fontSize: t.font.size.xs, color: t.color.mute, fontFamily: t.font.mono }}>
                {row.filename} · {row.format}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
