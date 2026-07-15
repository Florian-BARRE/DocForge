# ====== Code Summary ======
# SearchService — the app-side coordinator that runs the graph-based search pipeline against a real
# collection. It is the single invocation seam for the search graph (the /collections/{id}/search
# endpoint is NOT cut over to it yet — that is a later phase). Given a collection id + a raw query,
# it: loads the collection + its schema, builds the SearchContract run-input (the collection's OWN
# embedder, for the shared vector space), constructs the read-only CollectionReadPort scoped to that
# collection (the disabled-point exclusion baked in), assembles the run-input, and runs the stock
# search blob inline through the SearchRunner. Returns the terminal SearchResult.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.public_models.search import QueryFilters, RawQuery, SearchResult
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .contract import SearchContractBuilder
from .read_port import CollectionReadPortImpl
from .runner import SearchRunner

# The QuerySpec/RawQuery flag that turns the ColBERT late-interaction axis on for a run.
_LATE_INTERACTION_FLAG = "use_late_interaction"
# The retrieve node's id in the stock search blob, and its config key for the re-score pool depth.
_RETRIEVE_NODE_ID = "retrieve"
_RESCORE_POOL_SIZE_KEY = "rescore_pool_size"
# Wall-clock cap for an inline search run — search is sub-second; this only guards a stuck provider.
_RUN_TIMEOUT_SECONDS = 30.0


class SearchServiceError(Exception):
    """Raised when a search cannot run against a collection (unknown collection)."""


class SearchService(LoggerClass):
    """Coordinates a graph-based search run against a stored collection — the invocation seam."""

    def __init__(self, database: Database) -> None:
        """
        Args:
            database (Database): The shared data facade (collections + the read port's facades).
        """
        LoggerClass.__init__(self)
        self._database = database
        self._runner = SearchRunner()

    def __inject_rescore_pool_size(self, blob: GroupNodeBlob, rescore_pool_size: int) -> None:
        """
        Set the retrieve node's re-score pool depth in-place on the stock search blob.

        The graph's retrieve node reads its pool size from its NODE CONFIG
        (``RetrieveHybridConfig.rescore_pool_size``), which the default blob leaves at None (the
        port then falls back to its own default). A per-query override is honoured by writing the
        value onto the retrieve action node's raw config before build.

        Args:
            blob (GroupNodeBlob): The freshly built stock search blob (mutated in place).
            rescore_pool_size (int): The per-query fused-pool depth the ColBERT re-score works over.
        """
        # 1. Locate the retrieve action node in the flat stock blob and set its config key.
        for node in blob.nodes:
            if getattr(node, "id", None) == _RETRIEVE_NODE_ID:
                node.config[_RESCORE_POOL_SIZE_KEY] = rescore_pool_size
                return
        # 2. Not finding it means the stock topology drifted from _RETRIEVE_NODE_ID — the override
        #    would be silently lost, so surface it rather than degrade to the default unnoticed.
        self.logger.warning(
            f"rescore_pool_size override dropped: no '{_RETRIEVE_NODE_ID}' node in the search blob"
        )

    async def search(
        self,
        collection_id: uuid.UUID,
        query: str,
        *,
        top_k: int = 10,
        filters: dict | None = None,
        use_late_interaction: bool = False,
        rescore_pool_size: int | None = None,
    ) -> SearchResult:
        """
        Run the search graph against a collection and return the ranked SearchResult.

        Args:
            collection_id (uuid.UUID): The collection to search.
            query (str): The raw natural-language query.
            top_k (int): How many hits to return.
            filters (dict | None): The raw field → value filter map (None = no filters).
            use_late_interaction (bool): Opt into the ColBERT re-score (when the collection
                indexed ColBERT).
            rescore_pool_size (int | None): Per-query override for the fused candidate-pool depth
                the ColBERT late-interaction stage re-scores. None leaves the retrieve node's own
                config default (which itself defers to the store's port default of 100).

        Returns:
            SearchResult: The ranked hits, best first.

        Raises:
            SearchServiceError: When the collection is unknown.
            SearchContractError: When the collection has no embedder wired (from the contract builder).
            SearchRunError: When the graph is invalid or the run did not deliver (from the runner).
        """
        # 1. Load the collection + its schema — the contract source (embedder + filter surface).
        collection = await self._database.collections.get(collection_id)
        if collection is None:
            raise SearchServiceError(f"collection {collection_id} not found")
        schema = await self._database.collections.get_schema(collection_id)

        # 2. Build the run-input contract — the collection's OWN embedder (shared vector space).
        contract = SearchContractBuilder.build(collection, schema)

        # 3. Construct the read port scoped to this collection (exclusion baked into the facade).
        read_port = CollectionReadPortImpl(self._database, collection_id)

        # 4. Assemble the search run-input the graph binds by FromRunInput.
        run_input = {
            "query": RawQuery(
                text=query,
                top_k=top_k,
                flags={_LATE_INTERACTION_FLAG: use_late_interaction},
            ),
            "filters": QueryFilters(filters=filters or {}),
            "contract": contract,
        }

        # 5. Run the stock search graph inline (the per-collection search blob is a later phase);
        #    a per-query pool override is written onto the retrieve node's config before build.
        blob = SearchPipeline.default_blob()
        if rescore_pool_size is not None:
            self.__inject_rescore_pool_size(blob, rescore_pool_size)
        return await self._runner.run(
            blob, run_input, read_port, timeout_seconds=_RUN_TIMEOUT_SECONDS
        )


__all__ = ["SearchService", "SearchServiceError"]
