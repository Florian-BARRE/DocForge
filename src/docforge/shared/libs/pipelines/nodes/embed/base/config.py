# ====== Code Summary ======
# The config every embedder shares: the model identity (provenance, stored with the vectors),
# batching, and the switches — sparse vectors (when the provider supports them) and the per-field
# vectors of the contract's SEMANTIC (dense) and LEXICAL (sparse) chunk fields. Children add their
# endpoint.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import TimeoutRetryConfig


class BaseEmbedConfig(TimeoutRetryConfig):
    """Shared embedder config — children add their endpoint specifics.

    Timeout/retry come from ``TimeoutRetryConfig``; ``max_retries`` (3) and ``retry_backoff_seconds``
    (1.5) are overridden here to the embedder's own defaults, consumed by the embed node's retry +
    adaptive-split hand-loop. ``timeout_seconds`` keeps the mixin's 30 s here — the bge_server child
    overrides it to 60 s; the openai-compatible child keeps 30 s (unchanged).
    """

    model: str = Field(description="Embedding model name (provenance, stored with the vectors).")
    batch_size: int = Field(default=32, gt=0, description="Texts embedded per provider call.")
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Retries on a transient provider error (timeout/429/5xx) before a batch is "
        "split and its halves embedded independently. Counts retries BEYOND the initial call, so "
        "total attempts = 1 + max_retries (0 → a single one-shot attempt with no retry AND no "
        "adaptive split; 1 → 2 attempts; N → N+1) — the same TimeoutRetryConfig semantics the "
        "vlm/llm/NetworkRetry loops follow.",
    )
    retry_backoff_seconds: float = Field(
        default=1.5,
        ge=0,
        description="Base delay for the exponential backoff between retries (delay = base * attempt). "
        "Relaxed to allow 0 (the embed hand-loop treats 0 as no wait between retries).",
    )
    embed_sparse: bool = Field(
        default=True,
        description="Also produce the lexical sparse vectors (skipped when the provider "
        "does not support them).",
    )
    embed_semantic_fields: bool = Field(
        default=False,
        description="Also embed each SEMANTIC chunk-scope contract field's value as a named "
        "per-field dense vector (meta_<slug>_dense). The search path DOES query these — a "
        "semantic SearchTarget on the field routes the query's dense vector to that named vector. "
        "OFF by default because it costs one extra embedding call + vector storage per field per "
        "chunk; leave OFF unless you actually run metadata search against chunk-scope semantic "
        "fields.",
    )
    embed_lexical_fields: bool = Field(
        default=False,
        description="Also embed each LEXICAL chunk-scope contract field's value as a named "
        "per-field sparse vector (meta_<slug>_bm25), skipped when the provider has no sparse axis. "
        "The search path DOES query these — a lexical SearchTarget on the field routes the query's "
        "sparse vector to that named vector. OFF by default because it costs sparse encoding + "
        "vector storage per field per chunk; leave OFF unless you run lexical metadata search "
        "against chunk-scope fields.",
    )


__all__ = ["BaseEmbedConfig"]
