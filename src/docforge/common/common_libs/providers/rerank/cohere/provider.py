# ====== Code Summary ======
# CohereRerankProvider — external Cohere Rerank API client.
# Sends POST requests to the Cohere v2/rerank endpoint and returns scores
# in the original input order.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


class CohereRerankProvider(LoggerClass):
    """
    Cross-encoder reranking provider using the Cohere Rerank cloud API.

    Sends all candidates in a single request (Cohere handles batching server-side)
    and returns scores in the original input order.

    Attributes:
        _api_key (str): Cohere API key.
        _model (str): Cohere rerank model identifier (e.g. ``rerank-v3.5``).
    """

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.cohere.com/v2/rerank") -> None:
        """
        Initialize the Cohere reranking provider.

        Args:
            api_key (str): Cohere API key — required, must not be empty.
            model (str): Cohere rerank model (e.g. ``rerank-v3.5``).
            base_url (str): Cohere rerank endpoint (from the per-collection config; vendor default).
        """
        LoggerClass.__init__(self)
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self.logger.info(f"CohereRerankProvider initialized — model={self._model}")

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """
        Score each text against the query using the Cohere Rerank API.

        Sends a single request with all texts; Cohere returns results with an
        ``index`` field referencing the original position.  Scores are returned
        in the original input order (re-sorted by index).

        Args:
            query (str): The search query.
            texts (list[str]): Candidate texts to score.

        Returns:
            list[float]: Relevance scores aligned with the input ``texts`` list.

        Raises:
            httpx.HTTPStatusError: If the Cohere API returns a non-2xx response.
        """
        if not texts:
            return []

        # 1. Send all candidates to Cohere in one request
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "documents": texts, "model": self._model},
            )
            response.raise_for_status()
            data = response.json()

        # 2. Reconstruct scores in original input order (Cohere sorts by relevance)
        results = data.get("results", [])
        scores: list[float] = [0.0] * len(texts)
        for item in results:
            scores[item["index"]] = item["relevance_score"]

        return scores
