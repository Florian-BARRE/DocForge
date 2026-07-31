# ====== Code Summary ======
# The hybrid-retrieve node — the default retrieval method: it hands the query's vectors + filters to
# the bound CollectionReadPort, which runs ONE server-side hybrid search (dense+sparse fused with
# RRF, disabled points excluded) and returns the candidate pool. The node touches NO store directly:
# the read port arrives through the engine's bind() seam, so the graph controls what it may reach and
# the disabled-point exclusion can never be bypassed. Depth is the QuerySpec's over-sampled
# candidate_k; the node is a pure function of (input, injected port).

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, EncodedQuery, QuerySpec

# ====== Local Project Imports ======
from ...base import PortBackedNode


class RetrieveHybridConfig(NodeConfig):
    """The fusion strategy + the late-interaction re-score pool depth."""

    fusion: Literal["rrf", "dbsf"] = Field(
        default="rrf",
        description="How the dense and sparse branches are fused. 'rrf' (default) — Reciprocal "
        "Rank Fusion: rank-based, score-scale-agnostic, robust when the two axes disagree. 'dbsf' "
        "— Distribution-Based Score Fusion: normalises each branch's score distribution before "
        "summing, so a confident axis (e.g. exact lexical on IDs/codes) can dominate. Tune per "
        "collection to shift the semantic↔lexical balance.",
    )
    rescore_pool_size: int | None = Field(
        default=None,
        gt=0,
        description="Fused-pool size a ColBERT late-interaction re-score works over; None uses the "
        "store default. Only meaningful when the query carries a colbert vector.",
    )


class RetrieveHybridConsumes(NodeInput):
    """Input: the normalised query (filters/depth) + its encoded vectors."""

    spec: QuerySpec = Field(description="The normalised query — its filters and candidate_k depth.")
    encoded: EncodedQuery = Field(description="The query vectors driving the hybrid search.")


class RetrieveHybridProduces(NodeOutput):
    """Output: the candidate pool, best-first (fusion order)."""

    candidates: CandidateSet = Field(description="The retrieved candidate pool, best-first.")


@NodeRegistry.register("retrieve")
class RetrieveHybridNode(PortBackedNode):
    """Server-side hybrid retrieval (dense+sparse RRF) through the bound CollectionReadPort."""

    KIND = "hybrid"
    NAME = "Hybrid search"
    SUMMARY = "One server-side hybrid search (dense+sparse, RRF or DBSF), disabled points excluded."
    HOW_IT_WORKS = (
        "Passes the query's dense/sparse (and colbert) vectors + filters to the bound "
        "CollectionReadPort.hybrid_search, which fuses the modalities in the store with the "
        "configured strategy (RRF or DBSF) and excludes disabled chunks/documents. Returns "
        "candidate_k candidates in fusion order. No direct store import — the port is injected "
        "via bind()."
    )
    Config = RetrieveHybridConfig
    Consumes = RetrieveHybridConsumes
    Produces = RetrieveHybridProduces

    async def run(self, data: RetrieveHybridConsumes) -> RetrieveHybridProduces:
        """
        Retrieve the candidate pool through the bound read port.

        Args:
            data (RetrieveHybridConsumes): The query spec (filters/depth) + its encoded vectors.

        Returns:
            RetrieveHybridProduces: The candidate pool in fusion order.
        """
        config: RetrieveHybridConfig = self.config
        # 1. One read through the injected port — the exclusion invariant lives inside it. The
        #    spec's search targets select which named vectors (content and/or metadata) it queries;
        #    the port owns the target → vector-name resolution, so the node stays store-agnostic.
        candidates = await self._read_port.hybrid_search(
            encoded=data.encoded,
            filters=data.spec.filters,
            limit=data.spec.candidate_k,
            targets=data.spec.search_targets,
            rescore_pool_size=config.rescore_pool_size,
            fusion=config.fusion,
        )
        self.logger.debug(
            f"Retrieved {len(candidates)} candidate(s) (depth {data.spec.candidate_k})"
        )
        return RetrieveHybridProduces(candidates=CandidateSet(candidates=candidates))


__all__ = [
    "RetrieveHybridNode",
    "RetrieveHybridConfig",
    "RetrieveHybridConsumes",
    "RetrieveHybridProduces",
]
