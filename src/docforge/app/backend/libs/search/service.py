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
    default_content_targets,
)
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .contract import SearchContractBuilder
from .read_port import CollectionReadPortImpl
from .runner import SearchRunError, SearchRunner

# Default wall-clock cap for an inline search run when the caller does not configure one — search is
# sub-second; this only guards a stuck provider. Deployments override it via SEARCH_RUN_TIMEOUT_SECONDS.
_DEFAULT_RUN_TIMEOUT_SECONDS = 30.0


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
        # 2. Empty / sentinel → the stock default, serialised to the same plain-dict form (the
        #    default is freshly built from the current engine, so it needs no heal).
        return SearchPipeline.default_blob().model_dump(mode="json")

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

        # 4. Assemble the search run-input the graph binds by FromRunInput. None targets fall back
        #    to the content default so an untouched query behaves exactly as before targets existed.
        run_input = {
            "query": RawQuery(
                text=query,
                top_k=top_k,
                search_targets=search_targets or default_content_targets(),
                flags={},
            ),
            "filters": QueryFilters(filters=filters or {}),
            "contract": contract,
        }

        # 5. Resolve which search graph to run: the collection's OWN stored blob when it carries a
        #    topology, else the stock default. A broken stored blob makes the runner raise
        #    SearchRunError (at build + validate); the SEARCH ROUTER maps that to a 422 at the HTTP
        #    boundary, so an invalid stored graph is never surfaced as a 500.
        blob = self.__resolve_blob(collection.search)

        # 6. Price any search-time LLM spend against the collection's EFFECTIVE rates (canonical
        #    defaults folded with its per-collection overrides) — the same numbers the estimator/ingest
        #    meter use, so search cost is consistent with the rest of the platform's metering.
        rates = RateTable.from_overrides(getattr(collection, "estimate_overrides", None))
        return await self._runner.run(
            blob, run_input, read_port, rates, timeout_seconds=self._timeout_seconds
        )


__all__ = ["SearchService", "SearchServiceError"]
