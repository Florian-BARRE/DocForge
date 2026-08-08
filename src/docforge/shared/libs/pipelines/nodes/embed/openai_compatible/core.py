# ====== Code Summary ======
# The OpenAI-compatible embedder — dense vectors through any /v1/embeddings endpoint (OpenAI,
# vLLM, Infinity…) via the shared factory. The protocol has no sparse axis: the base skips it
# gracefully (dense-only collections).

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import (
    EndpointReachability,
    OpenAICompatConfig,
    OpenAICompatHelpers,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode


class EmbedOpenAICompatibleConfig(BaseEmbedConfig, OpenAICompatConfig):
    """OpenAI-compatible embeddings endpoint (endpoint fields inherited)."""


@NodeRegistry.register("embed")
class EmbedOpenAICompatibleNode(BaseEmbedderNode):
    """Dense embedding through any OpenAI-compatible /v1/embeddings endpoint."""

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible embeddings"
    SUMMARY = "Dense vectors through any OpenAI-compatible embeddings endpoint."
    HOW_IT_WORKS = (
        "Sends the text batches to the endpoint's /v1/embeddings route through the shared "
        "factory. The protocol carries no sparse vectors — the sparse axis is skipped."
    )
    Config = EmbedOpenAICompatibleConfig
    UNIQUE_IN_GRAPH = True

    async def preflight(self) -> None:
        """Verify the embeddings endpoint is reachable and its credentials accepted, before any spend."""
        config: EmbedOpenAICompatibleConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via the factory-built embeddings client."""
        config: EmbedOpenAICompatibleConfig = self.config
        return await OpenAICompatHelpers.embeddings(config).aembed_documents(texts)


__all__ = ["EmbedOpenAICompatibleNode", "EmbedOpenAICompatibleConfig"]
