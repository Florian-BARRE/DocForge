# ====== Code Summary ======
# Future fusion methods (SELECTABLE=False): RRF and weighted merges of two decomposed candidate
# pools into one scored pool. Registered with typed described faces for discoverability; bodies
# raise until the retrieve-decompose phase (research P3). The output is a ScoredCandidates so a later
# rerank/deliver step can read the aggregate score.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, ScoredCandidates

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _FusePlaceholderConfig(NodeConfig):
    """Knob-less config shared by the fusion placeholders."""


class _TwoPools(NodeInput):
    """Consumes the two per-modality candidate pools to fuse."""

    dense: CandidateSet = Field(description="The dense-branch candidate pool.")
    sparse: CandidateSet = Field(description="The sparse-branch candidate pool.")


class _FusedPool(NodeOutput):
    """Produces one fused, scored candidate pool."""

    fused: ScoredCandidates = Field(description="The fused, scored candidate pool.")


@NodeRegistry.register("fuse")
class FuseRrfNode(PlaceholderNode):
    """Reciprocal-rank fusion of the per-modality pools (future)."""

    KIND = "rrf"
    NAME = "RRF fusion"
    SUMMARY = "Reciprocal-rank fusion of the dense and sparse candidate pools."
    Config = _FusePlaceholderConfig
    Consumes = _TwoPools
    Produces = _FusedPool


@NodeRegistry.register("fuse")
class FuseWeightedNode(PlaceholderNode):
    """Weighted-sum fusion of the per-modality pools (future)."""

    KIND = "weighted"
    NAME = "Weighted fusion"
    SUMMARY = "Weighted-sum fusion of the dense and sparse candidate pools."
    Config = _FusePlaceholderConfig
    Consumes = _TwoPools
    Produces = _FusedPool


__all__ = ["FuseRrfNode", "FuseWeightedNode"]
