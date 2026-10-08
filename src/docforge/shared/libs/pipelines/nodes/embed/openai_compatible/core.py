# ====== Code Summary ======
# LEGACY single-provider embed node ``(embed, openai_compatible)`` — dense vectors through any
# OpenAI-compatible /v1/embeddings endpoint, in the shape stored before the dense/sparse slots. Kept
# registered but NOT selectable so a stored, not-yet-healed blob still builds; the stage reader
# migrates it to ``(embed, dense_sparse)`` with an openai_compatible dense slot and no sparse slot.
# Every wire call delegates to the shared OpenAICompatibleProvider (usage folded in there).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeUsage
from shared_libs.pipelines.nodes.openai_compat import (  # noqa: F401 — patch seam for tests
    OpenAICompatConfig,
    OpenAICompatHelpers,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode, EmbedConsumes, EmbedProduces
from ..providers import OpenAICompatibleProvider, OpenAICompatibleProviderConfig


class EmbedOpenAICompatibleConfig(BaseEmbedConfig, OpenAICompatConfig):
    """OpenAI-compatible embeddings endpoint (endpoint fields inherited)."""


@NodeRegistry.register("embed")
class EmbedOpenAICompatibleNode(BaseEmbedderNode):
    """LEGACY: dense embedding through an OpenAI-compatible endpoint (superseded by dense_sparse)."""

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible embeddings (legacy single-provider)"
    SUMMARY = "Legacy shape — read and migrated to the dense/sparse slot embedder."
    HOW_IT_WORKS = (
        "Kept only so blobs stored before the dense/sparse slots still build; the stage reader "
        "migrates it to (embed, dense_sparse) with an openai_compatible dense slot."
    )
    Config = EmbedOpenAICompatibleConfig
    UNIQUE_IN_GRAPH = True
    SELECTABLE = False

    def __init__(self, id: str, config: EmbedOpenAICompatibleConfig) -> None:
        """
        Args:
            id (str): Graph-unique identifier this node is wired under.
            config (EmbedOpenAICompatibleConfig): The endpoint config.
        """
        super().__init__(id, config)
        config: EmbedOpenAICompatibleConfig = self.config
        self.__provider = OpenAICompatibleProvider(
            OpenAICompatibleProviderConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
                preflight_timeout_seconds=config.preflight_timeout_seconds,
            )
        )

    def has_sparse(self) -> bool:
        """The OpenAI embeddings protocol carries no sparse vectors."""
        return False

    def _collect_usage(self) -> NodeUsage | None:
        """The provider's folded paid-call usage for this run."""
        return self.__provider.usage

    async def preflight(self) -> None:
        """Probe the /embeddings route before any spend."""
        await self.__provider.preflight()

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via the pooled OpenAI SDK client."""
        return await self.__provider.embed_dense(texts)

    async def run(self, data: EmbedConsumes) -> EmbedProduces:
        """Reset the provider's usage tally, then run the shared embed frame."""
        self.__provider.usage = None
        return await super().run(data)


__all__ = ["EmbedOpenAICompatibleNode", "EmbedOpenAICompatibleConfig"]
