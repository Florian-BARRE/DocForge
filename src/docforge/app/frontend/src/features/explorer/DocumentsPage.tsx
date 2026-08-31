// ====== Code Summary ======
// A collection's document catalogue — the explorer's entry point. One row per document; click
// opens the document page, delete removes it everywhere (two-step confirm, refetches the list).
// Rows are checkbox-selectable, and the toolbar's ReingestToolbar re-runs the FULL pipeline on
// the whole collection or the selected subset (jobs then show up on the collection's Jobs tab).

import { useEffect, useState } from "react";
import { deleteDocument, listDocuments, type DocumentListItem } from "../../api/explorer";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { DocumentRow } from "./DocumentRow";
import { ReingestToolbar } from "./ReingestToolbar";

interface DocumentsPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

const headStyle: React.CSSProperties = {
  textAlign: "left", color: theme.color.dim, fontSize: theme.font.size.xs,
  padding: `${theme.space.s}px ${theme.space.m}px`, fontWeight: 600,
  textTransform: "uppercase", letterSpacing: "0.04em",
  borderBottom: `1px solid ${theme.color.line}`,
};

export function DocumentsPage({ collectionId, onNavigate }: DocumentsPageProps) {
  const [documents, setDocuments] = useState<DocumentListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = () => {
    setError(null);
    listDocuments(collectionId)
      .then(setDocuments)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(() => {
    setSelected(new Set());
    load();
  }, [collectionId]);

  const handleDelete = async (documentId: string) => {
    await deleteDocument(documentId);
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(documentId);
      return next;
    });
    load();
  };

  const handleEnabledChanged = (documentId: string, enabled: boolean) => {
    setDocuments((prev) => (prev ? prev.map((doc) => (doc.id === documentId ? { ...doc, enabled } : doc)) : prev));
  };

  const toggleSelect = (documentId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(documentId)) next.delete(documentId);
      else next.add(documentId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelected((prev) => (documents && prev.size < documents.length ? new Set(documents.map((doc) => doc.id)) : new Set()));
  };

  const handleQueued = () => {
    setSelected(new Set());
    load();
  };

  const count = documents?.length ?? 0;
  // Only ids still present in the loaded list — never send a stale (deleted) id, which the
  // all-or-nothing subset validator would 422 the whole batch on.
  const selectedIds = documents ? documents.filter((doc) => selected.has(doc.id)).map((doc) => doc.id) : [];
  const allSelected = documents !== null && documents.length > 0 && selectedIds.length === documents.length;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      {documents && documents.length > 0 && (
        <div
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: theme.space.m, marginBottom: theme.space.l, flexWrap: "wrap",
          }}
        >
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.l }}>
            {count} document{count === 1 ? "" : "s"}
          </div>
          <ReingestToolbar
            collectionId={collectionId}
            totalCount={count}
            selectedIds={selectedIds}
            onQueued={handleQueued}
          />
        </div>
      )}
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !documents && <LoadingState label="loading documents…" />}
      {documents && documents.length === 0 && (
        <div
          style={{
            border: `1px dashed ${theme.color.lineStrong}`, borderRadius: theme.radius.l,
            padding: theme.space.xxl, textAlign: "center", color: theme.color.dim, fontSize: theme.font.size.l,
          }}
        >
          No documents yet — upload one from the collection page.
        </div>
      )}
      {documents && documents.length > 0 && (
        <div
          style={{
            background: theme.color.surface, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, overflow: "hidden",
          }}
        >
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th style={headStyle}>
                  <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} aria-label="Select all documents" />
                </th>
                <th style={headStyle}>Filename</th>
                <th style={headStyle}>Status</th>
                <th style={{ ...headStyle, textAlign: "right" }}>Pages</th>
                <th style={{ ...headStyle, textAlign: "right" }}>Size</th>
                <th style={headStyle}>Created</th>
                <th style={headStyle}>Enabled</th>
                <th style={headStyle} />
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  document={doc}
                  selected={selected.has(doc.id)}
                  onToggleSelect={toggleSelect}
                  onOpen={() => onNavigate({ name: "document", collectionId, documentId: doc.id })}
                  onDelete={() => handleDelete(doc.id)}
                  onEnabledChanged={(enabled) => handleEnabledChanged(doc.id, enabled)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
