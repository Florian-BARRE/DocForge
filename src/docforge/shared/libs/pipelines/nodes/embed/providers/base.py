# ====== Code Summary ======
# The embed PROVIDER contract — what fills one vector slot (dense or sparse) of the embed node. A
# provider is not a graph node: it is a config (``kind`` + endpoint/model/timeouts) and the batched
# encode calls the embed node drives inside its own retry/split + limiter frame. Each provider
# declares the axes it serves (dense / sparse), whether it can produce both in ONE call (a combined
# route — the embed node uses it when both slots point at the same endpoint), and whether its sparse
# vectors need the store's IDF modifier (a term-frequency encoder like bm25_local) — the vector
# schema of a collection is derived from that flag, never guessed.

# ====== Standard Library Imports ======
from abc import ABC
from enum import StrEnum
from typing import ClassVar

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig, NodeUsage
from shared_libs.public_models import SparseVector, TimeoutRetryConfig


class EmbedAxis(StrEnum):
    """The two vector axes a provider may fill."""

    DENSE = "dense"
    SPARSE = "sparse"


class EmbedRole(StrEnum):
    """What a batch of texts is — a provider may encode a long chunk body and a short value apart."""

    CONTENT = "content"
    FIELD = "field"


class EmbedProviderConfig(NodeConfig):
    """The config every provider slot shares: its kind (the dispatch key) and its model identity."""

    kind: str = Field(description="The provider kind filling this slot (e.g. bge_server).")
    model: str = Field(description="Model identity (provenance, stored with the vectors).")


class RemoteEmbedProviderConfig(EmbedProviderConfig, TimeoutRetryConfig):
    """A provider reached over HTTP: endpoint, key, retry policy and per-endpoint concurrency cap."""

    base_url: str = Field(description="The provider endpoint (e.g. http://bge_server:80).")
    api_key: str = Field(default="", description="Bearer token when the endpoint requires one.")
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Retries on a transient error (timeout/429/5xx) before the batch is split; total "
        "attempts = 1 + max_retries (0 → one shot, no retry and no adaptive split).",
    )
    retry_backoff_seconds: float = Field(
        default=1.5,
        ge=0,
        description="Base delay of the linear backoff between retries (delay = base * attempt).",
    )
    max_concurrency: int | None = Field(
        default=None,
        ge=1,
        description="Cap on concurrent in-flight requests to THIS endpoint across every worker (a "
        "shared Redis lease semaphore keyed by host:port). Unset → the deployment default "
        "(WORKER_EMBED_MAX_INFLIGHT_PER_ENDPOINT).",
    )

    @field_validator("base_url", "api_key", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


class EmbedProvider(ABC):
    """
    A slot provider: the batched encode calls behind one (or both) vector axes.

    Subclasses set ``KIND``, ``AXES``, ``Config`` and override the encode hooks of the axes they
    serve. Encode hooks return outputs aligned 1:1 with their input and RAISE on failure (the embed
    node retries/splits transient errors); only ``embed_dense_sparse`` may return None, meaning "no
    combined route on this server" (the node then falls back to two separate calls).
    """

    KIND: ClassVar[str] = ""
    AXES: ClassVar[frozenset[EmbedAxis]] = frozenset()
    SUPPORTS_COMBINED: ClassVar[bool] = False
    SPARSE_IDF: ClassVar[bool] = False
    Config: ClassVar[type[EmbedProviderConfig]] = EmbedProviderConfig

    def __init__(self, config: EmbedProviderConfig) -> None:
        """
        Args:
            config (EmbedProviderConfig): The validated slot config.
        """
        self.config = config
        # Paid-call token usage folded in by a hosted provider; a local/free one leaves it None.
        self.usage: NodeUsage | None = None

    @property
    def endpoint(self) -> str:
        """The provider's base URL ("" for an in-process provider — no remote capacity to guard)."""
        return getattr(self.config, "base_url", "")

    async def preflight(self) -> None:
        """Verify the endpoint is usable before spend — a no-op for an in-process provider."""
        return None

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors for a batch (only on a provider serving the dense axis)."""
        raise NotImplementedError(f"provider '{self.KIND}' has no dense axis")

    async def embed_sparse(
        self, texts: list[str], role: EmbedRole = EmbedRole.CONTENT
    ) -> list[SparseVector]:
        """Document-side sparse vectors for a batch (only on a provider serving the sparse axis)."""
        raise NotImplementedError(f"provider '{self.KIND}' has no sparse axis")

    async def embed_query_sparse(self, text: str) -> SparseVector:
        """The query-side sparse vector — identical to the document side unless overridden."""
        return (await self.embed_sparse([text], EmbedRole.FIELD))[0]

    async def embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Both axes in ONE call — None when this server has no combined route."""
        _ = texts
        return None

    def fold_usage(self, model: str, prompt_tokens: int) -> None:
        """Add a paid call's input tokens to the running usage (embeddings bill input only)."""
        prior = self.usage.prompt_tokens if self.usage is not None else 0
        self.usage = NodeUsage(
            model=model, prompt_tokens=prior + prompt_tokens, completion_tokens=0
        )


__all__ = [
    "EmbedAxis",
    "EmbedRole",
    "EmbedProviderConfig",
    "RemoteEmbedProviderConfig",
    "EmbedProvider",
]
