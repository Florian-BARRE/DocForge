# ---------------------- Value objects (nested in the flow artefacts) ---------------------- #
from .elements import Candidate, Hit

# ---------------------- Search selection (what to search) ---------------------- #
from .target import CONTENT_FIELD, SearchTarget, default_content_targets

# ---------------------- Run inputs (the typed entry contract) ---------------------- #
from .request import QueryFilters, RawQuery
from .contract import SearchContract

# ---------------------- Per-request tuning flags (reserved QuerySpec.flags keys) ---------------------- #
from .flags import FUSION_FLAG, FUSION_STRATEGIES, RERANK_FLAG

# ---------------------- Query-side flow artefacts ---------------------- #
from .query import EncodedQuery, QuerySpec

# ---------------------- Retrieval-side flow artefacts ---------------------- #
from .retrieval import CandidateSet, RankedHits, ScoredCandidates

# ---------------------- Terminal output contract ---------------------- #
from .result import SearchResult

# ------------------- Public API ------------------- #
__all__ = [
    "Candidate",
    "Hit",
    "SearchTarget",
    "CONTENT_FIELD",
    "default_content_targets",
    "RawQuery",
    "QueryFilters",
    "SearchContract",
    "RERANK_FLAG",
    "FUSION_FLAG",
    "FUSION_STRATEGIES",
    "QuerySpec",
    "EncodedQuery",
    "CandidateSet",
    "ScoredCandidates",
    "RankedHits",
    "SearchResult",
]
