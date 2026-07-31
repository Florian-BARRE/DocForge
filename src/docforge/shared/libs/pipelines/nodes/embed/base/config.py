# ====== Code Summary ======
# The config every embedder shares: the model identity (provenance, stored with the vectors),
# batching, and the two switches — sparse vectors (when the provider supports them) and the
# per-field vectors of the contract's SEMANTIC chunk fields. Children add their endpoint.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseEmbedConfig(NodeConfig):
    """Shared embedder config — children add their endpoint specifics."""

    model: str = Field(description="Embedding model name (provenance, stored with the vectors).")
    batch_size: int = Field(default=32, gt=0, description="Texts embedded per provider call.")
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Retries on a transient provider error (timeout/429/5xx) before a batch is "
        "split and its halves embedded independently. 0 disables retry AND the adaptive split.",
    )
    retry_backoff_seconds: float = Field(
        default=1.5,
        ge=0,
        description="Base delay for the exponential backoff between retries (delay = base * attempt).",
    )
    embed_sparse: bool = Field(
        default=True,
        description="Also produce the lexical sparse vectors (skipped when the provider "
        "does not support them).",
    )
    embed_semantic_fields: bool = Field(
        default=False,
        description="Also embed each SEMANTIC chunk-scope contract field's value as a named "
        "per-field vector. OFF by default: ingest writes these vectors but the search path does "
        "not query them yet, so leaving it on pays embedding + storage for unread vectors. Turn "
        "on once the semantic meta-field read side is wired (see the search endpoint).",
    )


__all__ = ["BaseEmbedConfig"]
