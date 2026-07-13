# ====== Code Summary ======
# Future per-modality retrieve methods (SELECTABLE=False): dense-only and sparse-only pools that a
# later fuse step joins. Registered for discoverability with correct typed described faces; their
# bodies raise until the retrieve-decompose phase (research P3).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet, EncodedQuery, QuerySpec

# ====== Local Project Imports ======
from ..placeholder import PlaceholderNode


class _RetrievePlaceholderConfig(NodeConfig):
    """Knob-less config shared by the per-modality retrieve placeholders."""


class _ModalityConsumes(NodeInput):
    """Consumes the query + its encoded vectors (one modality is read downstream)."""

    spec: QuerySpec = Field(description="The normalised query — its filters and candidate_k depth.")
    encoded: EncodedQuery = Field(description="The query vectors (the relevant modality is used).")


class _ModalityProduces(NodeOutput):
    """Produces a single-modality candidate pool."""

    candidates: CandidateSet = Field(description="The single-modality candidate pool, best-first.")


@NodeRegistry.register("retrieve")
class RetrieveDenseNode(PlaceholderNode):
    """Dense-only retrieval pool (future — joined by a fuse step)."""

    KIND = "dense"
    NAME = "Dense search"
    SUMMARY = "Dense-vector-only candidate pool (a decomposed branch joined by fuse)."
    Config = _RetrievePlaceholderConfig
    Consumes = _ModalityConsumes
    Produces = _ModalityProduces


@NodeRegistry.register("retrieve")
class RetrieveSparseNode(PlaceholderNode):
    """Sparse-only (lexical) retrieval pool (future — joined by a fuse step)."""

    KIND = "sparse"
    NAME = "Sparse search"
    SUMMARY = "Sparse-vector-only (lexical) candidate pool (a decomposed branch joined by fuse)."
    Config = _RetrievePlaceholderConfig
    Consumes = _ModalityConsumes
    Produces = _ModalityProduces


__all__ = ["RetrieveDenseNode", "RetrieveSparseNode"]
