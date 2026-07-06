// ====== Code Summary ======
// A collection's document catalogue — the explorer's entry point. One row per document; click
// opens the document page, delete removes it everywhere (two-step confirm, refetches the list).

import { useEffect, useState } from "react";
import { deleteDocument, listDocuments, type DocumentListItem } from "../../api/explorer";
import { BackLink } from "../../components/BackLink";
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
  padding: theme.space.s, fontWeight: 400, borderBottom: `1px solid ${theme.color.line}`,
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

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <BackLink label="Collection" onClick={() => onNavigate({ name: "collection", collectionId })} />
      <h1 style={{ fontSize: theme.font.size.xl, margin: `${theme.space.s}px 0 ${theme.space.l}px` }}>Documents</h1>
      {error && <ErrorState message={error} onRetry={load} />}
      {!error && !documents && <LoadingState label="loading documents…" />}
      {documents && documents.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          No documents yet — upload one from the collection page.
        </div>
      )}
      {documents && documents.length > 0 && (
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <th style={headStyle}>Filename</th>
              <th style={headStyle}>Status</th>
              <th style={{ ...headStyle, textAlign: "right" }}>Pages</th>
              <th style={{ ...headStyle, textAlign: "right" }}>Size</th>
              <th style={headStyle}>Created</th>
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
              />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
