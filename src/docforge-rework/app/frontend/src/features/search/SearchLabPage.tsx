// ====== Code Summary ======
// The Search Lab: run a query against this collection, tune result limit and the ColBERT late-
// interaction re-rank, inspect ranked hits. Nested under a collection like Documents/Jobs/Pipeline
// (collectionId is already known — no separate collection picker needed here).

import { useState } from "react";
import { search, type SearchResponse } from "../../api/search";
import { BackLink } from "../../components/BackLink";
import { ErrorState } from "../../components/ErrorState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { LateInteractionControls } from "./LateInteractionControls";
import { SearchQueryBar } from "./SearchQueryBar";
import { SearchResultsList } from "./SearchResultsList";

const DEFAULT_LIMIT = 10;
const DEFAULT_RESCORE_POOL_SIZE = 100;

interface SearchLabPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function SearchLabPage({ collectionId, onNavigate }: SearchLabPageProps) {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [lateInteraction, setLateInteraction] = useState(false);
  const [rescorePoolSize, setRescorePoolSize] = useState(DEFAULT_RESCORE_POOL_SIZE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);

  const runSearch = () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    search(collectionId, {
      query,
      limit,
      // Untouched = null, so the backend defers to the collection's saved search config.
      use_late_interaction: lateInteraction ? true : null,
      rescore_pool_size: lateInteraction ? rescorePoolSize : null,
    })
      .then(setResponse)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <BackLink label="Collection" onClick={() => onNavigate({ name: "collection", collectionId })} />
      <h1 style={{ fontSize: theme.font.size.xl, margin: `${theme.space.s}px 0 ${theme.space.l}px` }}>Search Lab</h1>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m, marginBottom: theme.space.l }}>
        <SearchQueryBar
          query={query}
          onQueryChange={setQuery}
          limit={limit}
          onLimitChange={setLimit}
          loading={loading}
          onSubmit={runSearch}
        />
        <LateInteractionControls
          enabled={lateInteraction}
          onEnabledChange={setLateInteraction}
          rescorePoolSize={rescorePoolSize}
          onRescorePoolSizeChange={setRescorePoolSize}
        />
      </div>

      {error && <ErrorState message={error} onRetry={runSearch} />}
      {!error && response && <SearchResultsList response={response} />}
    </div>
  );
}
