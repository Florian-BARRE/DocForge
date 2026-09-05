# ====== Code Summary ======
# The query-encode node — encodes the query into the SAME vector shapes the collection's chunks were
# indexed with, by rebuilding the collection's OWN embedder from the run-input SearchContract
# (registry class + extra="forbid" config, so a drifted blob fails loudly) and driving its embedding
# hooks on the single-element query batch. Dense always; sparse when the embedder carries the axis.
# This mirrors the app-side QueryEmbedder, expressed as a graph node. The provider HTTP call happens
# in-node — the same stateless read the ingest embed node makes; no store write, no hidden state.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search.nodes.query.base import QUERY_DEGRADED_FLAG
from shared_libs.public_models.search import EncodedQuery, QuerySpec, SearchContract

# The notes stamped on a degraded EncodedQuery — one per unavailable axis. They ride into
# SearchResult.debug so a caller sees WHY the result is partial (the embedder was saturated).
_DENSE_UNAVAILABLE = "semantic unavailable — embedder busy, lexical-only results"
_SPARSE_UNAVAILABLE = "lexical unavailable — embedder busy, semantic-only results"


class QueryEncodeError(Exception):
    """Raised when NO query vector axis could be produced (the embedder is unavailable).

    Distinct from a wiring/config error (those surface earlier, when the embedder is rebuilt): this
    means the encode calls themselves all failed — typically the shared embedder is saturated — so
    there is nothing to search on either axis. The runner maps it to a retryable 503, never a 422.
    """


class EncodeCollectionConfig(NodeConfig):
    """One knob — the per-axis encode timeout. The embedder itself is fully derived from the
    run-input contract (locked vector space); only WHEN we give up on a slow axis is configurable."""

    axis_timeout_seconds: float = Field(
        default=8.0,
        gt=0,
        description="Per-axis wall-clock cap (seconds) on the query embed call. A saturated embedder "
        "makes a single-query encode hang; without this the whole run would sit until the 30 s run "
        "cap (a 504) before ANY axis could be dropped. Bounding each axis well below the run cap "
        "makes a slow encode CATCHABLE — the axis is dropped and the surviving one answers "
        "lexical/semantic-only. Added with a safe default: a stored blob that omits it keeps 8 s.",
    )


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
        Encode the query into the collection's vector space, degrading per-axis under load.

        Each axis is encoded independently and fault-isolated: when the shared embedder is
        saturated (the query encode times out or errors) the axis is dropped and the surviving one
        drives a degraded retrieval, rather than hard-failing the whole search. A note is stamped on
        the result so the caller sees the result is partial. Only when NEITHER axis survives is a
        QueryEncodeError raised (there is nothing to search) — the runner maps that to a retryable
        503. A wiring/config error (rebuild) still raises loudly BEFORE any axis is attempted.

        Args:
            data (EncodeCollectionConsumes): The normalised query + the collection contract.

        Returns:
            EncodeCollectionProduces: The query's dense (and, when present, sparse) vectors, flagged
                ``degraded`` when an axis was dropped.

        Raises:
            QueryEncodeError: When no axis could be encoded (the embedder is unavailable).
        """
        embedder, config = EmbedBlobResolver.rebuild(
            data.contract.embed_kind,
            data.contract.embed_config,
            node_id=f"{self.id}_embedder",
        )
        text = data.spec.text
        timeout = self.config.axis_timeout_seconds
        notes: list[str] = []

        # 0. Carry through a degrade notice a query transform (rewrite/HyDE) left in the spec flags:
        #    the provider was down and the raw query was used. Folding it into the notes here is what
        #    makes that upstream fallback VISIBLE in SearchResult.debug rather than silent.
        query_degraded = data.spec.flags.get(QUERY_DEGRADED_FLAG)
        if query_degraded:
            notes.append(str(query_degraded))

        # 1. Dense — always attempted (a query without a dense vector loses its semantic axis). The
        #    embed call is bounded by a PER-AXIS timeout (asyncio.wait_for) well below the run's
        #    wall-clock cap: a saturated embedder makes it raise here (a catchable TimeoutError) long
        #    before the run cancels, so a surviving sparse axis can still answer rather than the whole
        #    run sinking to a 504. CancelledError (the run's wall-clock cap) is NOT an Exception, so
        #    it still propagates through wait_for and becomes the runner's timeout path.
        dense: list[float] = []
        try:
            dense = (await asyncio.wait_for(embedder._embed_dense([text]), timeout=timeout))[0]
        except Exception as exc:
            self.logger.warning(f"Dense query encode failed ({type(exc).__name__}: {exc})")
            notes.append(_DENSE_UNAVAILABLE)

        # 2. Sparse — only when the collection's embedder carries the lexical axis; fault-isolated and
        #    per-axis-bounded the same way so a dense-only survivor can still answer.
        sparse = None
        if config.embed_sparse:
            try:
                sparse_vectors = await asyncio.wait_for(
                    embedder._embed_sparse([text]), timeout=timeout
                )
                sparse = sparse_vectors[0] if sparse_vectors else None
            except Exception as exc:
                self.logger.warning(f"Sparse query encode failed ({type(exc).__name__}: {exc})")
                notes.append(_SPARSE_UNAVAILABLE)

        # 3. Neither axis survived — there is nothing to search. Fail loud so the runner can map it
        #    to a retryable 503 (the embedder is unavailable), not a misleading invalid-graph 422.
        if not dense and sparse is None:
            raise QueryEncodeError(
                "query encode produced no vector on any axis — the embedder is unavailable"
            )

        degraded = "; ".join(notes) or None
        self.logger.debug(
            f"Encoded query (model '{config.model}', sparse={sparse is not None}, "
            f"degraded={degraded is not None})"
        )
        return EncodeCollectionProduces(
            encoded=EncodedQuery(dense=dense, sparse=sparse, model=config.model, degraded=degraded)
        )


__all__ = [
    "EncodeCollectionNode",
    "EncodeCollectionConfig",
    "EncodeCollectionConsumes",
    "EncodeCollectionProduces",
]
