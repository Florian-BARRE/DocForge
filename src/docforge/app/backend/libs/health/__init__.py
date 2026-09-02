# ---------------------- Health composition service ---------------------- #
from .service import CollectionHealthService

# ---------------------- Graph-build (failure-captured) ---------------------- #
from .graph_builds import CollectionGraphBuilder, GraphBuildOutcome

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
