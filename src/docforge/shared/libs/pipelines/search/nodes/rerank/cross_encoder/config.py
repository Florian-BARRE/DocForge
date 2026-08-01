# ====== Code Summary ======
# RerankCrossEncoderConfig — the cross-encoder reranker's node config: the reranker endpoint (the
# in-stack bge_server /rerank route by default, so a stock rerank blob works with zero tuning) plus
# how much of the fused pool to re-score (top_n). extra="forbid": a typo in the stored blob fails the
# build loudly. The user never edits this — the canonical rerank blob carries it as-is.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig

# The in-stack bge_server reranker — the reachable default every stock rerank blob points at.
_DEFAULT_BASE_URL = "http://bge_server:80"
_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


class RerankCrossEncoderConfig(NodeConfig):
    """The cross-encoder reranker endpoint + how much of the fused pool to re-score."""

    base_url: str = Field(
        default=_DEFAULT_BASE_URL,
        description="Reranker endpoint — the in-stack bge_server /rerank route by default (free, "
        "local). A per-collection override points at any TEI-compatible reranker.",
    )
    model: str = Field(
        default=_DEFAULT_MODEL,
        description="Reranker model hosted by the server (provenance only — the /rerank route hosts "
        "one model and takes no model argument).",
    )
    api_key: str = Field(default="", description="Bearer token when the reranker requires one.")
    top_n: int = Field(
        default=50,
        gt=0,
        description="How many of the fused pool's TOP candidates (by fusion score) the cross-encoder "
        "re-scores. Kept oversized vs the delivered top_k so a single cheap pass covers the pool; "
        "candidates past top_n are dropped (they ranked below the re-scored set).",
    )
    timeout_seconds: float = Field(default=60.0, gt=0, description="Per-request timeout (s).")
    degrade_after_seconds: float = Field(
        default=12.0,
        gt=0,
        description="Wall-clock cap (seconds) on the rerank provider call. A reranker model cold-"
        "loads for ~30 s on its first call after idle; without this the whole search would sit "
        "until the 30 s run cap (a 504) before the slow rerank could be given up on. Bounding the "
        "call WELL BELOW the run cap makes a slow/cold reranker CATCHABLE — the node falls back to "
        "fusion-order candidates rather than sinking the search to a 504. Kept under "
        "timeout_seconds so this degrade fires first. Added with a safe default: a stored blob that "
        "omits it keeps 12 s.",
    )
    truncate: bool = Field(
        default=True,
        description="Truncate each (query, passage) pair to the reranker's max token length.",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


__all__ = ["RerankCrossEncoderConfig"]
