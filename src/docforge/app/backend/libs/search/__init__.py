# ---------------------- Run-input contract ---------------------- #
from .contract import SearchContractBuilder, SearchContractError

# ---------------------- Query-embedder reachability probe ---------------------- #
from .embedder_probe import QueryEmbedderProbe

# ---------------------- Read-only capability port ---------------------- #
from .read_port import CollectionReadPortImpl

# ---------------------- Inline runner ---------------------- #
from .runner import (
    SearchRunError,
    SearchRunner,
    SearchRunTimeout,
    SearchUnavailableError,
)

# ---------------------- Invocation seam ---------------------- #
from .service import SearchService, SearchServiceError

# ------------------- Public API ------------------- #
__all__ = [
    "SearchContractBuilder",
    "SearchContractError",
    "QueryEmbedderProbe",
    "CollectionReadPortImpl",
    "SearchRunner",
    "SearchRunError",
    "SearchRunTimeout",
    "SearchUnavailableError",
    "SearchService",
    "SearchServiceError",
]
