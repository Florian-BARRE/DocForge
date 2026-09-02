// ====== Code Summary ======
// The Search Lab: run a query against this collection, optionally narrow it with metadata filters,
// choose which targets (content and/or metadata fields) and modalities (semantic/lexical) the query
// searches, inspect ranked hits. Nested under a collection like Documents/Jobs/Pipeline (collectionId
// is already known — no separate collection picker needed here).

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { listDocuments } from "../../api/explorer";
import { classifySearchError, search, type SearchErrorInfo, type SearchResponse } from "../../api/search";
import { ErrorState } from "../../components/ErrorState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { SearchFilterBuilder } from "./SearchFilterBuilder";
import { SearchQueryBar } from "./SearchQueryBar";
import { SearchResultsList } from "./SearchResultsList";
import { buildSearchIn, DEFAULT_TARGET_SELECTION, SearchTargetPicker, type TargetSelection } from "./SearchTargetPicker";

const DEFAULT_LIMIT = 10;

interface SearchLabPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function SearchLabPage({ collectionId }: SearchLabPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [targetSelection, setTargetSelection] = useState<TargetSelection>(DEFAULT_TARGET_SELECTION);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<SearchErrorInfo | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  // `null` = not yet known (kept as "has documents" until it resolves, so the picker never flashes
  // disabled then enabled). Best-effort, mirrors the collection fetch below.
  const [hasDocuments, setHasDocuments] = useState<boolean | null>(null);

  // Best-effort: the filter builder is a supplementary affordance, so a failed fetch here
  // just means no filter section is offered — it never blocks the query bar.
  useEffect(() => {
    getCollection(collectionId).then(setCollection).catch(() => setCollection(null));
  }, [collectionId]);

  // Best-effort, same reasoning: only used to soften the "Search in" axis + explain a guaranteed
  // empty result on a brand-new collection, never to block the query bar itself.
  useEffect(() => {
    listDocuments(collectionId).then((docs) => setHasDocuments(docs.length > 0)).catch(() => setHasDocuments(true));
  }, [collectionId]);

  const filterableFields = (collection?.fields ?? []).filter((f) => f.filterable);

  const handleFilterChange = (fieldName: string, value: unknown | undefined) => {
    setFilters((prev) => {
      if (value === undefined) {
        const { [fieldName]: _omit, ...rest } = prev;
        return rest;
      }
      return { ...prev, [fieldName]: value };
    });
  };

  const handleTargetToggle = (field: string, modality: "semantic" | "lexical", checked: boolean) => {
    setTargetSelection((prev) => ({
      ...prev,
      [field]: { ...(prev[field] ?? { semantic: false, lexical: false }), [modality]: checked },
    }));
  };

  const runSearch = () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    search(collectionId, {
      query,
      limit,
      // No filter set → omitted entirely, so the backend defers to its defaults.
      filters: Object.keys(filters).length > 0 ? filters : null,
      // Default selection (content, both modalities) or nothing ticked → null, so the backend
      // defers to its own default path unchanged.
      search_in: buildSearchIn(targetSelection),
    })
      .then(setResponse)
      .catch((e) => setError(classifySearchError(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, overflowY: "auto", height: "100%", background: theme.color.bg }}>
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.l, marginBottom: theme.space.l }}>
          Run a query, narrow it with filters, and inspect the ranked hits.
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m, marginBottom: theme.space.l }}>
          <SearchQueryBar
            query={query}
            onQueryChange={setQuery}
            limit={limit}
            onLimitChange={setLimit}
            loading={loading}
            onSubmit={runSearch}
          />
          <SearchTargetPicker
            fields={collection?.fields ?? []}
            selection={targetSelection}
            onToggle={handleTargetToggle}
            emptyCollection={hasDocuments === false}
          />
          <SearchFilterBuilder fields={filterableFields} values={filters} onFilterChange={handleFilterChange} />
        </div>

        {/* A permanent config/auth fault (424) must NOT offer "retry" — only transient/timeout do. */}
        {error && (
          <ErrorState
            message={error.message}
            onRetry={error.kind === "config" ? undefined : runSearch}
          />
        )}
        {!error && response && <SearchResultsList response={response} />}
        {/* Pre-search placeholder — sits exactly where the hit-card column will render, left-aligned
            like the rest of this page (no extra centering/indent). */}
        {!error && !response && !loading && (
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
            Run a query to see ranked hits.
          </div>
        )}
      </div>
    </div>
  );
}
