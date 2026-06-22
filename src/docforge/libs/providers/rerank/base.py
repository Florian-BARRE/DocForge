# ====== Code Summary ======
# RerankProvider Protocol — the shared interface for all cross-encoder reranking backends.
# All concrete rerank providers (BGE-Reranker via TEI, Cohere Rerank, etc.) implement this.

# ====== Standard Library Imports ======
from typing import Protocol, runtime_checkable


@runtime_checkable
class RerankProvider(Protocol):
    """
    Shared interface for all cross-encoder reranking backends.

    Any class implementing this protocol can be used interchangeably as a reranker
    in SearchPipelineEngine.  Implementors must accept a query and a list of
    candidate texts and return a relevance score for each text in the same order
    as the input.
    """

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """
        Score each candidate text against the query using a cross-encoder model.

        Args:
            query (str): The user search query.
            texts (list[str]): Candidate texts to score (same order as retrieval results).

        Returns:
            list[float]: Relevance scores in the SAME ORDER as ``texts`` (not sorted).
                Higher scores indicate greater relevance.
        """
        ...
