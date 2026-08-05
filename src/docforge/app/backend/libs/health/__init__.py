# ---------------------- Health composition service ---------------------- #
from .service import CollectionHealthService

# ---------------------- Graph-build (failure-captured) ---------------------- #
from .graph_builds import CollectionGraphBuilder, GraphBuildOutcome

# ---------------------- Verdict roll-up ---------------------- #
from .verdict import HealthVerdictResolver

# ---------------------- API response contract ---------------------- #
from .models import (
    CollectionHealthResponse,
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
    "CollectionHealthResponse",
    "HealthVerdict",
    "IngestHealth",
    "SearchHealth",
    "SearchIndex",
    "SearchOperational",
]
