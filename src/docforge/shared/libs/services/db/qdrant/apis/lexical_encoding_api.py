# ====== Code Summary ======
# QdrantLexicalEncodingApi — reads which of a LIVE collection's metadata sparse vectors are in the
# local BM25 encoding (declared ``modifier=IDF``), so the meta-vector writer and the search read side
# pick the SAME encoder the stored vectors were built with. The test itself lives in
# QdrantVectorSchema.is_bm25_meta; this is only the read of the declared params.

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient

# ====== Local Project Imports ======
from ..vectors import QdrantVectorSchema


class QdrantLexicalEncodingApi:
    """Static read of a collection's metadata sparse-vector encodings."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "QdrantLexicalEncodingApi is a static-only class and cannot be instantiated."
        )

    @staticmethod
    async def bm25_meta_vectors(client: AsyncQdrantClient, name: str) -> set[str]:
        """
        The names of the collection's metadata sparse vectors that are BM25-encoded.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (must exist — the caller guards this).

        Returns:
            set[str]: The ``meta_<slug>_bm25`` vectors declared with ``modifier=IDF``; every other
                declared metadata sparse vector is in the legacy embedder (BGE-M3) encoding.
        """
        info = await client.get_collection(name)
        declared = info.config.params.sparse_vectors or {}
        return {
            vector
            for vector, params in declared.items()
            if QdrantVectorSchema.is_bm25_meta(vector, params)
        }


__all__ = ["QdrantLexicalEncodingApi"]
