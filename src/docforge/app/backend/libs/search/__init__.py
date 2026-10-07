# ---------------------- Run-input contract ---------------------- #
from .contract import SearchContractBuilder, SearchContractError

# ---------------------- Query-embedder reachability probe ---------------------- #
from .embedder_probe import QueryEmbedderProbe

# ---------------------- Read-only capability port ---------------------- #
from .read_port import CollectionReadPortImpl

# ---------------------- Built-graph pool ---------------------- #
from .graph_pool import BuiltGraphPool

# ---------------------- Inline runner ---------------------- #
from .runner import (
    SearchRunError,
    SearchRunner,
    SearchRunTimeout,
    SearchUnavailableError,
)

# ---------------------- Pure request gates + collection lookups ---------------------- #
from .collection_specs import SearchCollectionSpecs
from .enum_filter_canonicalizer import EnumFilterCanonicalizer
from .filter_validator import SearchFilterValidator
from .score_kind import ScoreKindClassifier
from .target_validator import SearchTargetValidator

# ---------------------- Filter value resolution + hints ---------------------- #
from .filter_hint import FilterHint
from .filter_resolution import FilterResolution
from .filter_resolver import SearchFilterResolver
from .min_score_hint import MinScoreHint
from .zero_hit_hints import ZeroHitHintBuilder

# ---------------------- Response shaping (projection + grouping) ---------------------- #
from .hit_projection import HitProjection
from .document_grouping import DocumentHitGrouper
from .result_finalizer import SearchResultFinalizer

# ---------------------- Per-request tuning ---------------------- #
from .tuning import SearchTuning, SearchTuningError

# ---------------------- Query-less browse ---------------------- #
from .browse_cursor import BrowseCursor, BrowseCursorError
from .chunk_browser import BrowsePage, ChunkBrowser

# ---------------------- Invocation seam ---------------------- #
from .service import SearchService, SearchServiceError

# ------------------- Public API ------------------- #
__all__ = [
    "SearchContractBuilder",
    "SearchContractError",
    "QueryEmbedderProbe",
    "CollectionReadPortImpl",
    "BuiltGraphPool",
    "SearchRunner",
    "SearchRunError",
    "SearchRunTimeout",
    "SearchUnavailableError",
    "SearchCollectionSpecs",
    "EnumFilterCanonicalizer",
    "SearchFilterValidator",
    "ScoreKindClassifier",
    "SearchTargetValidator",
    "FilterHint",
    "FilterResolution",
    "SearchFilterResolver",
    "MinScoreHint",
    "ZeroHitHintBuilder",
    "HitProjection",
    "DocumentHitGrouper",
    "SearchResultFinalizer",
    "SearchTuning",
    "SearchTuningError",
    "BrowseCursor",
    "BrowseCursorError",
    "BrowsePage",
    "ChunkBrowser",
    "SearchService",
    "SearchServiceError",
]
