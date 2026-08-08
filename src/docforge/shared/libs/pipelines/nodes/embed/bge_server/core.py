# ====== Code Summary ======
# The bge_server embedder — DocForge's own model host (BGE-M3): dense via /embed and sparse via
# /embed_sparse (TEI-compatible routes). The product default: one local server, both vector
# axes, no per-request model choice (the server hosts ONE model — the config's model field is
# provenance).

# ====== Third-Party Library Imports ======
import httpx
from pydantic import Field, field_validator

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from ..base import BaseEmbedConfig, BaseEmbedderNode


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
    """Dense + sparse embedding through DocForge's bge_server (BGE-M3)."""

    KIND = "bge_server"
    NAME = "bge_server (BGE-M3)"
    SUMMARY = "Dense + sparse vectors through DocForge's local BGE-M3 server."
    HOW_IT_WORKS = (
        "POSTs the text batches to the server's TEI-compatible routes: /embed_all for both axes in "
        "one forward pass when the server exposes it (falling back to /embed + /embed_sparse on an "
        "older server that answers 404). Both axes from one local server — the product default."
    )
    Config = EmbedBgeServerConfig
    UNIQUE_IN_GRAPH = True

    async def preflight(self) -> None:
        """Verify the bge_server is reachable and its token accepted, before any spend.

        Probes the TEI-compatible ``/health`` route — any answer (even non-200) proves the host
        is up; a 401/403 surfaces a rejected bearer token.
        """
        config: EmbedBgeServerConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
            path="/health",
        )

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

    @staticmethod
    def __parse_sparse(entries_per_input: list) -> list[SparseVector]:
        """Parse a TEI sparse payload — one {index, value} list per input — into SparseVectors."""
        return [
            SparseVector(
                indices=[int(entry["index"]) for entry in entries],
                values=[float(entry["value"]) for entry in entries],
            )
            for entries in entries_per_input
        ]

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via /embed."""
        return await self.__post("/embed", texts)

    async def _embed_sparse(self, texts: list[str]) -> list[SparseVector] | None:
        """Sparse vectors via /embed_sparse (TEI shape: one {index, value} list per input)."""
        return self.__parse_sparse(await self.__post("/embed_sparse", texts))

    async def _embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Dense + sparse in one forward pass via /embed_all — None when the server predates it.

        The single-pass optimisation: /embed_all returns ``{"dense": [...], "sparse": [...]}`` from
        one model call, halving the round-trips versus /embed + /embed_sparse. An older bge_server
        has no such route and answers 404; that specific "route absent" case is mapped to None so the
        caller falls back to the two separate routes. Genuine transient failures (timeouts, 5xx) are
        deliberately NOT swallowed — they propagate for the resilient retry/split to handle.
        """
        try:
            payload = await self.__post("/embed_all", texts)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise
        return payload["dense"], self.__parse_sparse(payload["sparse"])


__all__ = ["EmbedBgeServerNode", "EmbedBgeServerConfig"]
