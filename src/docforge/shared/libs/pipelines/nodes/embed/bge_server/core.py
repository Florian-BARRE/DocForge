# ====== Code Summary ======
# LEGACY single-provider embed node ``(embed, bge_server)`` — the shape every blob stored before the
# dense/sparse slots carried. Kept registered but NOT selectable so a stored, not-yet-healed blob still
# builds and its search/meta-sync readers still rebuild it; the stage reader migrates it to the
# ``(embed, dense_sparse)`` node (bge dense + bge sparse on the same endpoint when ``embed_sparse``).
# Every wire call delegates to the shared BgeServerProvider — no duplicated HTTP code.

# ====== Third-Party Library Imports ======
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode
from ..providers import BgeServerProvider, BgeServerProviderConfig


class EmbedBgeServerConfig(BaseEmbedConfig):
    """bge_server endpoint (the model is fixed server-side — the field is provenance)."""

    base_url: str = Field(description="bge_server endpoint (e.g. http://bge_server:80).")
    api_key: str = Field(default="", description="Bearer token when the server requires one.")
    model: str = Field(
        default="BAAI/bge-m3",
        description="Model hosted by the server (provenance, stored with the vectors).",
    )
    timeout_seconds: float = Field(default=60.0, gt=0, description="Per-request timeout (s).")

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_whitespace(cls, value: object) -> object:
        """Strip pasted whitespace — a trailing newline breaks the HTTP request line."""
        return value.strip() if isinstance(value, str) else value


@NodeRegistry.register("embed")
class EmbedBgeServerNode(BaseEmbedderNode):
    """LEGACY: dense + sparse through bge_server as one provider (superseded by dense_sparse)."""

    KIND = "bge_server"
    NAME = "bge_server (legacy single-provider)"
    SUMMARY = "Legacy shape — read and migrated to the dense/sparse slot embedder."
    HOW_IT_WORKS = (
        "Kept only so blobs stored before the dense/sparse slots still build; the stage reader "
        "migrates it to (embed, dense_sparse) with bge_server in both slots."
    )
    Config = EmbedBgeServerConfig
    UNIQUE_IN_GRAPH = True
    SELECTABLE = False

    def __provider(self) -> BgeServerProvider:
        """The shared provider over this node's endpoint (built per call — it is stateless)."""
        config: EmbedBgeServerConfig = self.config
        return BgeServerProvider(
            BgeServerProviderConfig(
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
                preflight_timeout_seconds=config.preflight_timeout_seconds,
            )
        )

    async def preflight(self) -> None:
        """Probe the server's /health before any spend."""
        await self.__provider().preflight()

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via /embed."""
        return await self.__provider().embed_dense(texts)

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Sparse vectors via /embed_sparse."""
        return await self.__provider().embed_sparse(texts)

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Both axes via /embed_all — None on an older server (404)."""
        return await self.__provider().embed_dense_sparse(texts)


__all__ = ["EmbedBgeServerNode", "EmbedBgeServerConfig"]
