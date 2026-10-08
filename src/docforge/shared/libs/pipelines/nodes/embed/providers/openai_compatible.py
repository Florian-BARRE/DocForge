# ====== Code Summary ======
# The openai_compatible provider — dense vectors through any OpenAI-compatible /v1/embeddings endpoint
# (OpenAI, vLLM, Infinity…) via the shared client pool. The protocol has no sparse axis, so it only
# ever fills the DENSE slot. Paid input tokens are folded into the provider's usage for the cost meter.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import (
    EndpointReachability,
    LangChainClientPool,
    OpenAICompatHelpers,
)

# ====== Local Project Imports ======
from .base import EmbedAxis, EmbedProvider, RemoteEmbedProviderConfig
from .registry import EmbedProviderRegistry


class OpenAICompatibleProviderConfig(RemoteEmbedProviderConfig):
    """An OpenAI-compatible embeddings endpoint (dense only)."""

    kind: Literal["openai_compatible"] = Field(
        default="openai_compatible", description="Provider kind."
    )


@EmbedProviderRegistry.register
class OpenAICompatibleProvider(EmbedProvider):
    """Dense embedding through any OpenAI-compatible /v1/embeddings endpoint."""

    KIND = "openai_compatible"
    AXES = frozenset({EmbedAxis.DENSE})
    Config = OpenAICompatibleProviderConfig

    @staticmethod
    def __prompt_tokens(response: object) -> int | None:
        """The input tokens a response bills (None when the endpoint omits usage)."""
        usage = getattr(response, "usage", None)
        raw = getattr(usage, "prompt_tokens", None)
        if raw is None:
            raw = getattr(usage, "total_tokens", None)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    async def preflight(self) -> None:
        """Probe the /embeddings ROUTE (a TEI-only server answers on the host but has no such route)."""
        config: OpenAICompatibleProviderConfig = self.config  # type: ignore[assignment]
        await EndpointReachability.check_route_present(
            node_kind=self.KIND,
            base_url=config.base_url,
            path="/embeddings",
            capability_hint=(
                "this provider needs an OpenAI-compatible /v1/embeddings endpoint; this looks like a "
                "TEI-only server (routes /embed, not /embeddings). Use the bge_server provider for a "
                "TEI/bge_server host, or point base_url at an endpoint ending in /v1"
            ),
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors through the pooled OpenAI SDK client (usage folded in, order restored)."""
        config: OpenAICompatibleProviderConfig = self.config  # type: ignore[assignment]
        response = await LangChainClientPool.arun(
            lambda: OpenAICompatHelpers.embeddings(config),
            lambda client: client.async_client.create(input=texts, model=config.model),
            label=f"embed '{self.KIND}'",
        )
        tokens = self.__prompt_tokens(response)
        if tokens is not None:
            self.fold_usage(config.model, tokens)
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


__all__ = ["OpenAICompatibleProvider", "OpenAICompatibleProviderConfig"]
