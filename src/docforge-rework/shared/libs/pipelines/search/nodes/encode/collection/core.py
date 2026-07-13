# ====== Code Summary ======
# The query-encode node — encodes the query into the SAME vector shapes the collection's chunks were
# indexed with, by rebuilding the collection's OWN embedder from the run-input SearchContract
# (registry class + extra="forbid" config, so a drifted blob fails loudly) and driving its embedding
# hooks on the single-element query batch. Dense always; sparse when the embedder carries the axis;
# ColBERT only when late interaction is requested AND the collection indexed it. This mirrors the
# app-side QueryEmbedder, expressed as a graph node. The provider HTTP call happens in-node — the
# same stateless read the ingest embed node makes; no store write, no hidden state.

# ====== Standard Library Imports ======
from typing import cast

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
import shared_libs.pipelines.nodes.embed  # noqa: F401 — ensures every embedder self-registers
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import EncodedQuery, QuerySpec, SearchContract

# The registry family every embedder self-registers under (never string-literalled elsewhere).
_EMBED_FAMILY = "embed"
# The QuerySpec flag that turns the ColBERT late-interaction axis on for this run.
_LATE_INTERACTION_FLAG = "use_late_interaction"


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

    encoded: EncodedQuery = Field(description="The query vectors (dense; sparse/colbert when indexed).")


@NodeRegistry.register("encode")
class EncodeCollectionNode(ActionNode):
    """Encode the query with the collection's OWN embedder (dense always, sparse/colbert per config)."""

    KIND = "collection"
    NAME = "Collection embedder"
    SUMMARY = "Encode the query into the collection's vector space using its own embedder."
    HOW_IT_WORKS = (
        "Rebuilds the collection's embedder from the run-input contract (registry class + validated "
        "config), then drives its embedding hooks on the single query: /embed for the dense vector, "
        "/embed_sparse when the axis exists, /embed_colbert only when late interaction is on and the "
        "collection indexed ColBERT. Locked to one method — the query must share the chunks' space."
    )
    Config = EncodeCollectionConfig
    Consumes = EncodeCollectionConsumes
    Produces = EncodeCollectionProduces
    UNIQUE_IN_GRAPH = True

    def __rebuild_embedder(self, contract: SearchContract) -> tuple[BaseEmbedderNode, BaseEmbedConfig]:
        """Rebuild the collection's embedder from its stored blob (class + validated config)."""
        # 1. Resolve the registered embedder class (bge_server, openai_compatible, …).
        node_class = cast(type[BaseEmbedderNode], NodeRegistry.get(_EMBED_FAMILY, contract.embed_kind))
        # 2. Re-validate the stored config (extra="forbid" — a drifted blob fails loudly).
        config = cast(BaseEmbedConfig, node_class.Config(**contract.embed_config))
        # 3. A throwaway instance — only its embedding hooks are exercised (never wired in a graph).
        return node_class(id=f"{self.id}_embedder", config=config), config

    async def run(self, data: EncodeCollectionConsumes) -> EncodeCollectionProduces:
        """
        Encode the query into the collection's vector space.

        Args:
            data (EncodeCollectionConsumes): The normalised query + the collection contract.

        Returns:
            EncodeCollectionProduces: The query's dense (and, when present, sparse/colbert) vectors.
        """
        embedder, config = self.__rebuild_embedder(data.contract)
        text = data.spec.text

        # 1. Dense — always (a query without a dense vector cannot be searched).
        dense = (await embedder._embed_dense([text]))[0]

        # 2. Sparse — only when the collection's embedder carries the lexical axis.
        sparse = None
        if config.embed_sparse:
            sparse_vectors = await embedder._embed_sparse([text])
            sparse = sparse_vectors[0] if sparse_vectors else None

        # 3. ColBERT — only when this run asks for late interaction AND the collection indexed it.
        colbert = None
        if data.spec.flags.get(_LATE_INTERACTION_FLAG) and embedder._wants_colbert():
            colbert = (await embedder._embed_colbert([text]))[0]

        self.logger.debug(
            f"Encoded query (model '{config.model}', sparse={sparse is not None}, "
            f"colbert={colbert is not None})"
        )
        return EncodeCollectionProduces(
            encoded=EncodedQuery(dense=dense, sparse=sparse, colbert=colbert, model=config.model)
        )


__all__ = [
    "EncodeCollectionNode",
    "EncodeCollectionConfig",
    "EncodeCollectionConsumes",
    "EncodeCollectionProduces",
]
