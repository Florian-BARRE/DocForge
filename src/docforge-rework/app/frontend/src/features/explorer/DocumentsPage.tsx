// ====== Code Summary ======
// A collection's document catalogue — the explorer's entry point. One row per document; click
// opens the document page, delete removes it everywhere (two-step confirm, refetches the list).

import { useEffect, useState } from "react";
import { deleteDocument, listDocuments, type DocumentListItem } from "../../api/explorer";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { DocumentRow } from "./DocumentRow";

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

  const load = () => {
    setError(null);
    listDocuments(collectionId)
      .then(setDocuments)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  const handleDelete = async (documentId: string) => {
    await deleteDocument(documentId);
    load();
  };

  const handleEnabledChanged = (documentId: string, enabled: boolean) => {
    setDocuments((prev) => (prev ? prev.map((doc) => (doc.id === documentId ? { ...doc, enabled } : doc)) : prev));
  };

  const count = documents?.length ?? 0;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", maxWidth: 1200, margin: "0 auto", width: "100%" }}>
      {documents && documents.length > 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.l, marginBottom: theme.space.l }}>
          {count} document{count === 1 ? "" : "s"}
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
