# ====== Code Summary ======
# SearchContractBuilder — turns a stored Collection into the SearchContract run-input the search
# graph's encode node consumes. It locates the collection's OWN embed node in its serialised
# pipeline blob (the same node the chunks were indexed with) so the query encodes in the SAME vector
# space as ingestion — the non-negotiable shared-vector-space invariant. Only the embedder is
# carried; target/filter validation is done router-side against the live schema. Mirrors how the
# live QueryEmbedder derives its embedder from the pipeline blob, expressed as a run-input contract.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models.search import SearchContract
from shared_libs.services.db.postgresql.tables import Collection


class SearchContractError(Exception):
    """Raised when a collection cannot yield a search contract (no embedder wired)."""


class SearchContractBuilder:
    """Static builder of the SearchContract run-input from a stored collection."""

    logger = loggerplusplus.bind(identifier="SearchContractBuilder")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchContractBuilder is a static-only class and cannot be instantiated.")

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
        embed_node = EmbedBlobResolver.find_embed_node(collection.pipeline)
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
