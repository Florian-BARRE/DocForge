# ====== Code Summary ======
# CollectionReadPort — the read-only capability a retrieve/hydrate node reaches through the engine's
# bind() seam (never by importing a client/facade). It is the ONLY door a search graph has onto the
# stores, and it is read-only by construction: the disabled-chunk / disabled-document exclusion is
# baked into hybrid_search, so NO composed graph can ever fetch a disabled point. This keeps a node
# pure (a stateless function of input + capability) while letting the retrieve step BE the graph.
#
# Wave 1 defines the interface + the capability key + the typed accessor. Wave 2 injects a concrete
# implementation (over SearchFacade.hybrid) through a request-context capability resolver at bind().

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.public_models.search import Candidate, EncodedQuery, Hit, SearchTarget

# The key a bound capabilities mapping stores the read port under (never string-literalled in a node).
COLLECTION_READ_CAPABILITY = "collection_read"


class CollectionReadPort(ABC):
    """
    The read-only retrieval capability injected into search nodes via ``bind()``.

    A retrieve/hydrate node calls this port instead of importing a store client, so the engine
    controls what a search graph may reach. Both methods are read-only and stateless from the
    node's point of view; the disabled-point exclusion is enforced INSIDE hybrid_search and cannot
    be bypassed by any composed graph.
    """

    @abstractmethod
    async def hybrid_search(
        self,
        encoded: EncodedQuery,
        filters: dict,
        limit: int,
        targets: list[SearchTarget],
        rescore_pool_size: int | None = None,
        fusion: str = "rrf",
    ) -> list[Candidate]:
        """
        Run the collection's filtered hybrid search and return candidates, best-first.

        The implementation MUST bake in the searchability exclusion (enabled chunks only, disabled
        documents removed) so a disabled point can never surface, whatever the graph wiring. The
        ``targets`` select WHICH named vectors the SAME query vectors are compared against — content
        and/or metadata fields, each on its semantic (dense) and/or lexical (sparse) axis; resolving
        a target to its Qdrant vector name is the implementation's concern, kept out of the nodes.

        Args:
            encoded (EncodedQuery): The query's vectors (dense always; sparse/colbert when present).
            filters (dict): The structured filter map (field → value) to constrain the search.
            limit (int): The candidate depth to return (the QuerySpec's ``candidate_k``).
            targets (list[SearchTarget]): The fields × modalities to search (content and/or metadata).
            rescore_pool_size (int | None): The fused-pool size a late-interaction re-score works
                over; None to leave the store's default.
            fusion (str): Branch-fusion strategy — "rrf" (default) or "dbsf".

        Returns:
            list[Candidate]: Chunk ids + scores in fusion order (empty when nothing matched).
        """
        ...

    @abstractmethod
    async def hydrate(self, chunk_ids: list[str]) -> dict[str, Hit]:
        """
        Fetch the rich fields (document_id, text, metadata) for each chunk id — read-only Postgres.

        Args:
            chunk_ids (list[str]): The candidate chunk ids to hydrate.

        Returns:
            dict[str, Hit]: chunk_id → Hit carrying document_id/text/metadata (score/rank left at
                their defaults; the calling node assigns the authoritative rank/score). A chunk id
                absent from the map has no row (deleted between search and hydration) and is skipped.
        """
        ...


def read_port(capabilities: Any) -> CollectionReadPort:
    """
    Read the bound CollectionReadPort out of a node's injected capabilities.

    Args:
        capabilities (Any): The value ``bind()`` stored on the node (the capabilities mapping).

    Returns:
        CollectionReadPort: The bound read port.

    Raises:
        RuntimeError: If no capabilities were bound, or none carries the read port — a wiring
            error surfaced at run time (the node ran before its capability was injected).
    """
    # 1. The node must have been bound before it runs (Wave 2's resolver does this at build time).
    if not isinstance(capabilities, dict) or COLLECTION_READ_CAPABILITY not in capabilities:
        raise RuntimeError(
            f"CollectionReadPort not bound: capability '{COLLECTION_READ_CAPABILITY}' is missing. "
            "The node ran before its read port was injected via bind()."
        )
    # 2. Hand back the typed port.
    return capabilities[COLLECTION_READ_CAPABILITY]


__all__ = ["CollectionReadPort", "COLLECTION_READ_CAPABILITY", "read_port"]
