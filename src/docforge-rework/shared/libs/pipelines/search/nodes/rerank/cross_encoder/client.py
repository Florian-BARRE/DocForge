# ====== Code Summary ======
# CrossEncoderRerankClient — the tiny HTTP client for the bge_server (TEI-compatible) /rerank route.
# It is the SAME category of in-node provider call the embed node makes: a stateless POST, no store,
# no hidden state. It sends {query, texts, truncate} and returns each candidate's (index, score) pair
# (score sigmoid-normalised to [0, 1]), where index is the passage's position in the input texts —
# the caller maps the score back onto its candidate by that index. The reranker hosts one model, so
# no model argument is sent (the config's model field is provenance only). API keys are never logged.

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


class CrossEncoderRerankClient(LoggerClass):
    """Stateless HTTP client for a TEI-compatible cross-encoder /rerank endpoint."""

    def __init__(self, base_url: str, api_key: str, timeout_seconds: float) -> None:
        """
        Args:
            base_url (str): The reranker endpoint (the in-stack bge_server by default).
            api_key (str): Bearer token when the endpoint requires one (never logged).
            timeout_seconds (float): Per-request timeout in seconds.
        """
        LoggerClass.__init__(self)
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def rerank(
        self, query: str, texts: list[str], truncate: bool
    ) -> list[tuple[int, float]]:
        """
        Score each candidate passage against the query with the cross-encoder reranker.

        Args:
            query (str): The query text every passage is scored against.
            texts (list[str]): The candidate passages, in candidate order.
            truncate (bool): Truncate each (query, passage) pair to the model's max length.

        Returns:
            list[tuple[int, float]]: One (index, score) per candidate — index is the passage's
                position in ``texts``, score is the sigmoid-normalised relevance in [0, 1].
        """
        # 1. Bearer auth only when a key is configured (local endpoints ignore it).
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

        # 2. One batched POST — the whole cut pool scored in a single round-trip.
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_seconds
        ) as client:
            response = await client.post(
                "/rerank",
                json={"query": query, "texts": texts, "truncate": truncate},
                headers=headers,
            )
            response.raise_for_status()

        # 3. Return the (index, score) pairs — the caller re-maps them onto its candidates.
        payload = response.json()
        self.logger.debug(f"Reranked {len(payload)} candidate(s)")
        return [(int(item["index"]), float(item["score"])) for item in payload]


__all__ = ["CrossEncoderRerankClient"]
