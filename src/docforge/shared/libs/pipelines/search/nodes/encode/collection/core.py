# ====== Code Summary ======
# The query-encode node — encodes the query into the SAME vector shapes the collection's chunks were
# indexed with, by rebuilding the collection's OWN embedder from the run-input SearchContract
# (registry class + extra="forbid" config, so a drifted blob fails loudly) and driving its embedding
# hooks on the single-element query batch. Dense always; sparse when the embedder carries the axis.
# This mirrors the app-side QueryEmbedder, expressed as a graph node. The provider HTTP call happens
# in-node — the same stateless read the ingest embed node makes; no store write, no hidden state.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import EncodedQuery, QuerySpec, SearchContract


class EncodeCollectionConfig(NodeConfig):
    """No knob — the embedder is fully derived from the run-input contract (locked vector space)."""


class EncodeCollectionConsumes(NodeInput):
    """Input: the normalised query + the collection contract carrying its embedder blob."""

    spec: QuerySpec = Field(description="The normalised query whose text is encoded.")
    contract: SearchContract = Field(
        description="The collection contract carrying the embedder kind + config to rebuild."
    )


class EncodeCollectionProduces(NodeOutput):
    """Output: the query's vectors in the collection's own vector space."""

    encoded: EncodedQuery = Field(description="The query vectors (dense; sparse when indexed).")


@NodeRegistry.register("encode")
class EncodeCollectionNode(ActionNode):
    """Encode the query with the collection's OWN embedder (dense always, sparse per config)."""

    KIND = "collection"
    NAME = "Collection embedder"
    SUMMARY = "Encode the query into the collection's vector space using its own embedder."
    HOW_IT_WORKS = (
        "Rebuilds the collection's embedder from the run-input contract (registry class + validated "
        "config), then drives its embedding hooks on the single query: /embed for the dense vector "
        "and /embed_sparse when the axis exists. Locked to one method — the query must share the "
        "chunks' space."
    )
    Config = EncodeCollectionConfig
    Consumes = EncodeCollectionConsumes
    Produces = EncodeCollectionProduces
    UNIQUE_IN_GRAPH = True

    async def run(self, data: EncodeCollectionConsumes) -> EncodeCollectionProduces:
        """
        Encode the query into the collection's vector space.

        Args:
            data (EncodeCollectionConsumes): The normalised query + the collection contract.

        Returns:
            EncodeCollectionProduces: The query's dense (and, when present, sparse) vectors.
        """
        embedder, config = EmbedBlobResolver.rebuild(
            data.contract.embed_kind,
            data.contract.embed_config,
            node_id=f"{self.id}_embedder",
        )
        text = data.spec.text

        # 1. Dense — always (a query without a dense vector cannot be searched).
        dense = (await embedder._embed_dense([text]))[0]

        # 2. Sparse — only when the collection's embedder carries the lexical axis.
        sparse = None
        if config.embed_sparse:
            sparse_vectors = await embedder._embed_sparse([text])
            sparse = sparse_vectors[0] if sparse_vectors else None

        self.logger.debug(f"Encoded query (model '{config.model}', sparse={sparse is not None})")
        return EncodeCollectionProduces(
            encoded=EncodedQuery(dense=dense, sparse=sparse, model=config.model)
        )


__all__ = [
    "EncodeCollectionNode",
    "EncodeCollectionConfig",
    "EncodeCollectionConsumes",
    "EncodeCollectionProduces",
]
