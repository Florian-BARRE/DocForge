# ---------------------- Health composition service ---------------------- #
from .service import CollectionHealthService

# ---------------------- Graph-build (failure-captured) ---------------------- #
from .graph_builds import CollectionGraphBuilder, GraphBuildOutcome

# ---------------------- Buildability cache ---------------------- #
from .buildability_cache import BuildabilityCache

# ---------------------- Verdict roll-up ---------------------- #
from .verdict import HealthRollup, HealthVerdictResolver

# ---------------------- API response contract ---------------------- #
from .models import (
    CollectionHealthResponse,
    CollectionHealthSummary,
    CollectionListVerdict,
    HealthVerdict,
    IngestHealth,
    SearchHealth,
    SearchIndex,
    SearchOperational,
)

# ------------------- Public API ------------------- #
__all__ = [
    "CollectionHealthService",
    "CollectionGraphBuilder",
    "GraphBuildOutcome",
    "BuildabilityCache",
    "HealthVerdictResolver",
    "HealthRollup",
    "CollectionHealthResponse",
    "CollectionHealthSummary",
    "CollectionListVerdict",
    "HealthVerdict",
    "IngestHealth",
    "SearchHealth",
    "SearchIndex",
    "SearchOperational",
]
