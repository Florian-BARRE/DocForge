# ====== Code Summary ======
# RerankProvider Protocol — defines the interface for post-retrieval reranking backends
# that score candidate passages against a query for relevance ordering.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Protocol, runtime_checkable

# ====== Third-Party Library Imports ======
# (none — Protocol and result types only)
# ====== Internal Project Imports ======
from common_libs.providers.results import RerankResult

# ====== Local Project Imports ======
# (none)


@runtime_checkable
class RerankProvider(Protocol):
    """Scores a list of candidate passages against a query for post-retrieval reranking."""

    name: str
    version: str
    runs_on: str

    async def rerank(self, query: str, docs: list[str]) -> RerankResult:
        """
        Rerank candidate passages for relevance to the query.

        Args:
            query (str): The retrieval query.
            docs (list[str]): Candidate passage texts.

        Returns:
            RerankResult: Relevance score per candidate, same order as input.
        """
        ...
