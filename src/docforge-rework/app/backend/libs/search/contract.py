# ====== Code Summary ======
# SearchContractBuilder — turns a stored Collection into the SearchContract run-input the search
# graph's encode node consumes. It locates the collection's OWN embed node in its serialised
# pipeline blob (the same node the chunks were indexed with) so the query encodes in the SAME vector
# space as ingestion — the non-negotiable shared-vector-space invariant. Only the embedder is
# carried; target/filter validation is done router-side against the live schema. Mirrors how the
# live QueryEmbedder derives its embedder from the pipeline blob, expressed as a run-input contract.

# ====== Standard Library Imports ======
from collections.abc import Iterator
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models.search import SearchContract
from shared_libs.services.db.postgresql.tables import Collection

# The registry family every embedder self-registers under (never string-literalled elsewhere).
_EMBED_FAMILY = "embed"


class SearchContractError(Exception):
    """Raised when a collection cannot yield a search contract (no embedder wired)."""


class SearchContractBuilder:
    """Static builder of the SearchContract run-input from a stored collection."""

    logger = loggerplusplus.bind(identifier="SearchContractBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchContractBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def __iter_action_blobs(cls, blob: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield every action-node dict in a (possibly nested) group/foreach pipeline blob."""
        # 1. A foreach wraps a single group body — descend into it.
        if "body" in blob:
            yield from cls.__iter_action_blobs(blob["body"])
        # 2. A group holds children — descend into each.
        elif "nodes" in blob:
            for child in blob["nodes"]:
                yield from cls.__iter_action_blobs(child)
        # 3. A leaf action carries a family — it is what we iterate over.
        elif blob.get("family"):
            yield blob

    @classmethod
    def __embed_node(cls, pipeline: dict[str, Any]) -> dict[str, Any] | None:
        """Find the collection's embed node dict in its serialised pipeline blob (single-use)."""
        # 1. The embed family is single-use, so the first embed node is THE one.
        for node in cls.__iter_action_blobs(pipeline):
            if node.get("family") == _EMBED_FAMILY:
                return node
        return None

    @classmethod
    def build(cls, collection: Collection) -> SearchContract:
        """
        Build the search run-input contract from a stored collection.

        Args:
            collection (Collection): The collection being searched (its pipeline blob carries the
                embed node; its id scopes the read port).

        Returns:
            SearchContract: identity + the collection's OWN embedder (kind + config).

        Raises:
            SearchContractError: When the collection's pipeline has no embed node — it was never
                indexed, so there is no vector space to encode the query into.
        """
        # 1. Locate the collection's embed node — the query must share the chunks' vector space.
        embed_node = cls.__embed_node(collection.pipeline)
        if embed_node is None:
            raise SearchContractError(
                f"Collection {collection.id} has no embed node — search is unavailable."
            )

        # 2. Assemble the run-input contract (embed config re-validated when the encode node runs).
        #    Only the embedder is carried — target/filter validation is done router-side against the
        #    live schema, so no field-list surface travels on the contract.
        return SearchContract(
            collection_id=str(collection.id),
            embed_kind=embed_node["kind"],
            embed_config=dict(embed_node.get("config", {})),
        )


__all__ = ["SearchContractBuilder", "SearchContractError"]
