# ====== Code Summary ======
# The bge_server provider — DocForge's own model host (BGE-M3, TEI-compatible routes): dense via
# /embed, sparse (learned weights, no IDF modifier) via /embed_sparse, and BOTH in one forward pass via
# /embed_all — the combined route the embed node uses when its dense AND sparse slots point at the
# same bge_server. An older server without /embed_all answers 404 → None (the node falls back).

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
import httpx
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.public_models import SparseVector

# ====== Local Project Imports ======
from .base import EmbedAxis, EmbedProvider, EmbedRole, RemoteEmbedProviderConfig
from .registry import EmbedProviderRegistry


class BgeServerProviderConfig(RemoteEmbedProviderConfig):
    """bge_server endpoint (the model is fixed server-side — the field is provenance)."""

    kind: Literal["bge_server"] = Field(default="bge_server", description="Provider kind.")
    model: str = Field(
        default="BAAI/bge-m3",
        description="Model hosted by the server (provenance, stored with the vectors).",
    )
    timeout_seconds: float = Field(default=60.0, gt=0, description="Per-request timeout (s).")


@EmbedProviderRegistry.register
class BgeServerProvider(EmbedProvider):
    """Dense + sparse (+ combined) embedding through DocForge's bge_server."""

    KIND = "bge_server"
    AXES = frozenset({EmbedAxis.DENSE, EmbedAxis.SPARSE})
    SUPPORTS_COMBINED = True
    Config = BgeServerProviderConfig

    async def __post(self, route: str, texts: list[str]) -> list | dict:
        """One batched POST — the pooled client self-heals a dead socket after a server restart."""
        config: BgeServerProviderConfig = self.config  # type: ignore[assignment]
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}

        async def _post(client: httpx.AsyncClient) -> list | dict:
            response = await client.post(route, json={"inputs": texts}, headers=headers)
            response.raise_for_status()
            return response.json()

        return await HttpClientPool.run(
            _post, base_url=config.base_url, timeout=config.timeout_seconds
        )

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

    async def preflight(self) -> None:
        """Probe /health — any answer proves the host is up; 401/403 surfaces a rejected token."""
        config: BgeServerProviderConfig = self.config  # type: ignore[assignment]
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
            path="/health",
        )

    async def embed_dense(self, texts: list[str]) -> list[list[float]]:
        """Dense vectors via /embed."""
        return await self.__post("/embed", texts)  # type: ignore[return-value]

    async def embed_sparse(
        self, texts: list[str], role: EmbedRole = EmbedRole.CONTENT
    ) -> list[SparseVector]:
        """Sparse vectors via /embed_sparse (learned weights — the role changes nothing)."""
        _ = role
        return self.__parse_sparse(await self.__post("/embed_sparse", texts))  # type: ignore[arg-type]

    async def embed_dense_sparse(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[SparseVector]] | None:
        """Both axes in one forward pass via /embed_all — None on an older server (404).

        Only the "route absent" signal maps to None; a timeout/5xx propagates for the node's
        resilient retry/split.
        """
        try:
            payload = await self.__post("/embed_all", texts)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise
        return payload["dense"], self.__parse_sparse(payload["sparse"])  # type: ignore[index]


__all__ = ["BgeServerProvider", "BgeServerProviderConfig"]
