# ====== Code Summary ======
# BgeRerankProvider — local BGE-Reranker-v2-m3 cross-encoder served via TEI.
# Sends batched POST requests to the TEI /rerank endpoint and returns scores
# in the original input order (TEI returns sorted by score descending).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import httpx
from loggerplusplus import LoggerClass


class BgeRerankProvider(LoggerClass):
    """
    Cross-encoder reranking provider backed by BAAI/bge-reranker-v2-m3 via TEI.

    Sends texts to a running TEI /rerank endpoint in batches and returns scores in
    the original input order.  TEI returns results sorted by score descending; this
    class re-sorts by original index so the caller can zip with their result list.

    Attributes:
        _base_url (str): TEI server base URL (e.g. ``http://bge:80``).
        _batch_size (int): Maximum number of texts per HTTP request.
        runs_on (str): "local" or "remote" — set from the locality flag.
    """

    runs_on: str = "local"

    def __init__(self, base_url: str, batch_size: int, locality: str = "local", api_key: str = "") -> None:
        """
        Initialize the BGE reranking provider.

        Args:
            base_url (str): TEI server base URL (e.g. ``http://bge:80``).
            batch_size (int): Maximum number of texts per HTTP request to TEI.
            locality (str): "local" or "external" — sets runs_on for the device gate.
            api_key (str): Optional bearer token (sent as Authorization when non-empty).
        """
        LoggerClass.__init__(self)
        self._base_url = base_url.rstrip("/")
        self._batch_size = batch_size
        self.runs_on = "remote" if locality == "external" else "local"
        self._headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.logger.info(
            f"BgeRerankProvider initialized — locality={locality} url={self._base_url} batch_size={self._batch_size}"
        )

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """
        Score each text against the query using the cross-encoder and return scores in original order.

        Splits texts into batches of at most ``_batch_size`` elements, sends each batch
        to TEI's /rerank endpoint, then reassembles scores in the original input order.

        Args:
            query (str): The search query.
            texts (list[str]): Candidate texts to score (same indexing as retrieval results).

        Returns:
            list[float]: Relevance scores aligned with the input ``texts`` list.

        Raises:
            httpx.HTTPStatusError: If TEI returns a non-2xx response.
        """
        if not texts:
            return []

        # 1. Split into batches to avoid overwhelming the TEI server
        batches = [
            texts[i: i + self._batch_size]
            for i in range(0, len(texts), self._batch_size)
        ]

        # 2. Collect scores for each batch; offset_index tracks absolute position
        scores: list[tuple[int, float]] = []
        offset = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            for batch in batches:
                batch_scores = await self._rerank_batch(client, query, batch, offset)
                scores.extend(batch_scores)
                offset += len(batch)

        # 3. Sort by original index and return flat score list
        scores.sort(key=lambda t: t[0])
        return [s for _, s in scores]

    async def _rerank_batch(
        self,
        client: httpx.AsyncClient,
        query: str,
        texts: list[str],
        offset: int,
    ) -> list[tuple[int, float]]:
        """
        Send one batch to TEI and return (absolute_index, score) pairs.

        TEI /rerank response: ``[{"index": int, "score": float}, ...]`` sorted by score descending.
        The ``index`` field is relative to the batch, so we add ``offset`` to get the absolute index.

        Args:
            client (httpx.AsyncClient): Active HTTP client.
            query (str): Search query.
            texts (list[str]): Batch of candidate texts.
            offset (int): Absolute position of the first text in this batch.

        Returns:
            list[tuple[int, float]]: (absolute_index, score) pairs for the batch.
        """
        response = await client.post(
            f"{self._base_url}/rerank",
            json={"query": query, "texts": texts, "truncate": True},
            headers=self._headers,
        )
        response.raise_for_status()
        data = response.json()
        return [(item["index"] + offset, item["score"]) for item in data]
