# ====== Code Summary ======
# SearchService — the app-side coordinator that runs the graph-based search pipeline against a real
# collection. It is the single invocation seam for the search graph. Given a collection id + a raw
# query, it: loads the collection + its schema, builds the SearchContract run-input (the collection's
# OWN embedder, for the shared vector space), constructs the read-only CollectionReadPort scoped to
# that collection (the disabled-point exclusion baked in), assembles the run-input, RESOLVES the
# search blob to run (the collection's own stored search graph when it carries one, else the stock
# default), and runs it inline through the SearchRunner. Returns the terminal SearchResult.

# ====== Standard Library Imports ======
import uuid
from functools import lru_cache
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.search import (
    SearchBlobNormalizationError,
    SearchBlobNormalizer,
    SearchPipeline,
)
from shared_libs.public_models.search import (
    QueryFilters,
    RawQuery,
    SearchResult,
    SearchTarget,
)
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from ..blob_hash import BlobHasher
from .contract import SearchContractBuilder
from .read_port import CollectionReadPortImpl
from .runner import SearchRunError, SearchRunner

# Default wall-clock cap for an inline search run when the caller does not configure one — search is
# sub-second; this only guards a stuck provider. Deployments override it via SEARCH_RUN_TIMEOUT_SECONDS.
_DEFAULT_RUN_TIMEOUT_SECONDS = 30.0

# The pool cache key for the stock default search graph — a constant sentinel so the common case
# (collection.search == {}) never needs to be hashed; stored blobs key by their content hash instead.
_STOCK_DEFAULT_KEY = "__stock_default_search__"


@lru_cache(maxsize=1)
def _default_search_blob() -> dict:
    """
    The serialised stock search blob, built ONCE per process and reused.

    Returning the one memoized dict is safe: the builder only ``model_validate``s it (never mutates
    it), so every resolver/runner treats it read-only — the same contract the old per-request
    ``model_dump`` relied on.

    Returns:
        dict: The stock search topology in plain-dict form.
    """
    return SearchPipeline.default_blob().model_dump(mode="json")


class SearchServiceError(Exception):
    """Raised when a search cannot run against a collection (unknown collection)."""


class SearchService(LoggerClass):
    """Coordinates a graph-based search run against a stored collection — the invocation seam."""

    def __init__(
        self, database: Database, timeout_seconds: float = _DEFAULT_RUN_TIMEOUT_SECONDS
    ) -> None:
        """
        Args:
            database (Database): The shared data facade (collections + the read port's facades).
            timeout_seconds (float): Wall-clock cap for one inline search run (guards a stuck/cold
                provider). Deployments pass SEARCH_RUN_TIMEOUT_SECONDS; defaults to 30 s.
        """
        LoggerClass.__init__(self)
        self._database = database
        self._runner = SearchRunner()
        self._timeout_seconds = timeout_seconds

    def __resolve_blob(self, stored: dict) -> dict:
        """
        Pick the search blob to run: the collection's own stored graph, else the stock default.

        The ``collection.search`` column is a SEARCH GRAPH BLOB (the search analog of
        ``collection.pipeline``). A built blob is a group carrying a ``"nodes"`` list; ``{}`` (or
        anything without ``"nodes"``) is the sentinel meaning "the collection has no configured
        search — use the product's stock topology". This is the seam that makes search as
        configurable as ingestion.

        A stored graph is AUTO-HEALED at read via the SearchBlobNormalizer (the search analog of the
        ingest BlobNormalizer): registry drift — a config field renamed/removed since the blob was
        saved — is reconciled to the current node models so a stale stored search self-heals at read
        instead of bricking the run. This is the READ-side complement to the write-time fail-fast
        validation; a heal that cannot reconcile the blob is a genuinely invalid stored graph,
        surfaced as a SearchRunError (the router maps it to the same 422 as an unbuildable blob).

        Args:
            stored (dict): The raw ``collection.search`` value.

        Returns:
            dict: The blob to run, always in plain-dict form (the runner accepts either form).

        Raises:
            SearchRunError: The stored graph cannot be reconciled to the current engine (re-save it).
        """
        # 1. A stored graph (has "nodes") is the collection's OWN configured search — heal it to the
        #    current registry, then run it. An unreconcilable blob is an invalid stored graph.
        if stored.get("nodes"):
            try:
                return SearchBlobNormalizer.normalize(stored)
            except SearchBlobNormalizationError as exc:
                raise SearchRunError(str(exc)) from exc
        # 2. Empty / sentinel → the memoized stock default (built once per process, treated
        #    read-only), serialised to the same plain-dict form; the default needs no heal.
        return _default_search_blob()

    def __cache_key(self, stored: dict, resolved: dict) -> str:
        """
        The pool cache key for a resolved blob — sentinel for the stock default, else a content hash.

        Args:
            stored (dict): The raw ``collection.search`` value (decides default vs configured).
            resolved (dict): The healed blob actually run — hashed so two stores that heal to the
                same graph reuse the same built graph.

        Returns:
            str: The stock-default sentinel, or the resolved blob's stable content hash.
        """
        # 1. A configured topology keys by its healed content; the empty sentinel skips hashing.
        if stored.get("nodes"):
            return BlobHasher.digest(resolved)
        return _STOCK_DEFAULT_KEY

    async def search(
        self,
        collection_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: dict | None = None,
        search_targets: list[SearchTarget] | None = None,
        collection: Any | None = None,
    ) -> tuple[SearchResult, tuple[int, int, float | None, int]]:
        """
        Run the search graph against a collection and return the ranked SearchResult plus its cost.

        Args:
            collection_id (uuid.UUID): The collection to search.
            query (str): The raw natural-language query.
            top_k (int): How many hits to return.
            filters (dict | None): The raw field → value filter map (None = no filters).
            search_targets (list[SearchTarget] | None): The fields × modalities to search (content
                and/or metadata). None searches content on both axes (unchanged default).

        Returns:
            tuple[SearchResult, tuple[int, int, float | None, int]]: the ranked hits (best first) and
                the run's priced usage (prompt tokens, completion tokens, USD cost or None, count) —
                any search-time LLM spend (rewrite/HyDE), priced against the collection's own rates.

        Raises:
            SearchServiceError: When the collection is unknown.
            SearchContractError: When the collection has no embedder wired (from the contract builder).
            SearchRunError: When the graph is invalid or the run did not deliver (from the runner).
        """
        # 1. The collection is the contract source (its pipeline blob carries the embedder). Reuse the
        #    one the caller already loaded (the router loads it for its 404/409 gates) to avoid a
        #    second round-trip + re-decode of the large {pipeline, search} JSONB on the hot path.
        if collection is None:
            collection = await self._database.collections.get(collection_id)
        if collection is None:
            raise SearchServiceError(f"collection {collection_id} not found")

        # 2. Build the run-input contract — the collection's OWN embedder (shared vector space).
        contract = SearchContractBuilder.build(collection)

        # 3. Construct the read port scoped to this collection (exclusion baked into the facade).
        read_port = CollectionReadPortImpl(self._database, collection_id)

        # 4. Assemble the search run-input the graph binds by FromRunInput. When the caller named no
        #    targets we pass an EMPTY list through, so the normalize node owns the content-target
        #    default (its content_modalities config — the dense_only preset's seam). For the stock
        #    'hybrid' config that default is both axes, exactly as before targets existed.
        run_input = {
            "query": RawQuery(
                text=query,
                top_k=top_k,
                search_targets=search_targets or [],
                flags={},
            ),
            "filters": QueryFilters(filters=filters or {}),
            "contract": contract,
        }

        # 5. Resolve which search graph to run: the collection's OWN stored blob when it carries a
        #    topology, else the stock default. A broken stored blob makes the runner raise
        #    SearchRunError (at build + validate); the SEARCH ROUTER maps that to a 422 at the HTTP
        #    boundary, so an invalid stored graph is never surfaced as a 500.
        stored_search = collection.search or {}
        blob = self.__resolve_blob(stored_search)
        graph_key = self.__cache_key(stored_search, blob)

        # 6. Price any search-time LLM spend against the collection's EFFECTIVE rates (canonical
        #    defaults folded with its per-collection overrides) — the same numbers the estimator/ingest
        #    meter use, so search cost is consistent with the rest of the platform's metering.
        rates = RateTable.from_overrides(getattr(collection, "estimate_overrides", None))
        return await self._runner.run(
            blob,
            run_input,
            read_port,
            rates,
            graph_key=graph_key,
            timeout_seconds=self._timeout_seconds,
        )


__all__ = ["SearchService", "SearchServiceError"]
