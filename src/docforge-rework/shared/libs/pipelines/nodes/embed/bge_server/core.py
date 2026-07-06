# ====== Code Summary ======
# The bge_server embedder — DocForge's own model host (BGE-M3): dense via /embed and sparse via
# /embed_sparse (TEI-compatible routes). The product default: one local server, both vector
# axes, no per-request model choice (the server hosts ONE model — the config's model field is
# provenance).

# ====== Third-Party Library Imports ======
import httpx
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode


class EmbedBgeServerConfig(BaseEmbedConfig):
    """bge_server endpoint (the model is fixed server-side — the field is provenance)."""

    base_url: str = Field(description="bge_server endpoint (e.g. http://bge_server:8008).")
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
    """Dense + sparse embedding through DocForge's bge_server (BGE-M3)."""

    KIND = "bge_server"
    NAME = "bge_server (BGE-M3)"
    SUMMARY = "Dense + sparse vectors through DocForge's local BGE-M3 server."
    HOW_IT_WORKS = (
        "POSTs the text batches to the server's TEI-compatible routes: /embed for the dense "
        "vectors and /embed_sparse for the lexical ones. Both axes from one local server — "
        "the product default."
    )
    Config = EmbedBgeServerConfig
    UNIQUE_IN_GRAPH = True

    async def __post(self, route: str, texts: list[str]) -> list:
        """One batched call to the server."""
        config: EmbedBgeServerConfig = self.config
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        async with httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds
        ) as client:
            response = await client.post(route, json={"inputs": texts}, headers=headers)
            response.raise_for_status()
        return response.json()

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via /embed."""
        return await self.__post("/embed", texts)

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Sparse vectors via /embed_sparse (TEI shape: one {index, value} list per input)."""
        payload = await self.__post("/embed_sparse", texts)
        return [
            SparseVector(
                indices=[int(entry["index"]) for entry in entries],
                values=[float(entry["value"]) for entry in entries],
            )
            for entries in payload
        ]


__all__ = ["EmbedBgeServerNode", "EmbedBgeServerConfig"]
