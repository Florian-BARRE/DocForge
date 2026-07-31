// ====== Code Summary ======
// The Search Lab: run a query against this collection, optionally narrow it with metadata filters,
// choose which targets (content and/or metadata fields) and modalities (semantic/lexical) the query
// searches, inspect ranked hits. Nested under a collection like Documents/Jobs/Pipeline (collectionId
// is already known — no separate collection picker needed here).

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { search, type SearchResponse } from "../../api/search";
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
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  // Best-effort: the filter builder is a supplementary affordance, so a failed fetch here
  // just means no filter section is offered — it never blocks the query bar.
  useEffect(() => {
    getCollection(collectionId).then(setCollection).catch(() => setCollection(null));
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
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
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
          <SearchTargetPicker fields={collection?.fields ?? []} selection={targetSelection} onToggle={handleTargetToggle} />
          <SearchFilterBuilder fields={filterableFields} values={filters} onFilterChange={handleFilterChange} />
        </div>

        {error && <ErrorState message={error} onRetry={runSearch} />}
        {!error && response && <SearchResultsList response={response} />}
      </div>
    </div>
  );
}
