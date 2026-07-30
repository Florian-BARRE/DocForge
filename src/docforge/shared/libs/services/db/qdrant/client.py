# ====== Code Summary ======
# QdrantClient — the low-level connection gateway to Qdrant, the vector-store analogue of
# PostgresClient. It owns the single async client; the qdrant apis (collection / index / search) run
# their operations against it. `raw` exposes that client the way PostgresClient exposes a session —
# nothing else constructs a Qdrant connection.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from qdrant_client import AsyncQdrantClient


class QdrantClient(LoggerClass):
    """Connection gateway to Qdrant — owns the async client the apis run against."""

    def __init__(self, url: str, api_key: str | None = None, timeout: float = 60.0) -> None:
        """
        Args:
            url (str): Qdrant endpoint (e.g. ``http://qdrant:6333``).
            api_key (str | None): Optional API key.
            timeout (float): Per-request timeout in seconds. The qdrant-client default (5s) is too
                low for ColBERT multi-vector upserts (dozens–hundreds of vectors/point, indexed with
                ``wait=true``), which intermittently exceed it; 60s covers a heavy batch.
        """
        LoggerClass.__init__(self)
        self._client = AsyncQdrantClient(url=url, api_key=api_key, timeout=timeout)
        self.logger.info(f"QdrantClient connected to {url}")

    @property
    def raw(self) -> AsyncQdrantClient:
        """The underlying async client the qdrant apis operate on (like PostgresClient.session())."""
        return self._client

    async def close(self) -> None:
        """Close the client's connections — call on shutdown."""
        await self._client.close()


__all__ = ["QdrantClient"]
