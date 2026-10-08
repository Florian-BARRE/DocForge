# ====== Code Summary ======
# ContentSparseReencoder — the rebuild_index path for a content sparse vector the OLD store holds from
# ANOTHER sparse provider (its IDF modifier disagrees with the configured one, or the indexed embed
# baseline's sparse half differs from the config — e.g. bge server A → B, same modifier), or does not
# hold at all (a sparse slot switched on after ingest). An index rebuild copies vectors and cannot invent them,
# but the content sparse vector is cheap to recompute: ``chunk.text`` in Postgres IS the enriched text
# the embedder encoded, so each copied batch's texts are re-encoded through the collection's
# configured sparse provider (``_embed_sparse``, the same hook as ingest) and written with the copy.
# Points without a Postgres chunk (orphans the post-swap reconcile purges) get no vector.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.base import BaseEmbedderNode
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi
from shared_libs.services.db.qdrant import DeclaredVectors, SparseVec, VectorNames

# The provider batch size when the embedder config carries none.
_DEFAULT_BATCH_SIZE = 32


class ContentSparseReencoder(LoggerClass):
    """Re-encode content sparse vectors of copied points from their Postgres chunk text."""

    def __init__(self, postgres: PostgresClient, embedder: BaseEmbedderNode) -> None:
        """
        Args:
            postgres (PostgresClient): The chunk-text source.
            embedder (BaseEmbedderNode): The collection's embedder (its sparse slot encodes).
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._embedder = embedder
        self._batch_size = int(getattr(embedder.config, "batch_size", _DEFAULT_BATCH_SIZE))

    async def __texts(self, point_ids: list[str]) -> list[tuple[str, str]]:
        """``(point id, chunk text)`` for every id that is a Postgres chunk (input order kept)."""
        ids = [uuid.UUID(point_id) for point_id in point_ids]
        async with self._postgres.session() as session:
            chunks = await ChunkApi.get_by_ids(session, ids)
        texts = {str(chunk.id): chunk.text for chunk in chunks}
        return [(point_id, texts[point_id]) for point_id in point_ids if point_id in texts]

    @staticmethod
    def needed(old: DeclaredVectors, layout: VectorLayout, sparse_changed: bool = False) -> bool:
        """Whether the rebuilt store's content sparse vector must be re-encoded, not copied.

        True when the config has a sparse slot and the old store's content sparse vector is absent,
        declared under the other IDF modifier, or was indexed by another sparse provider config
        (``sparse_changed`` — the store cannot tell two non-IDF encoders apart, the baseline can).
        """
        content = VectorNames.CONTENT_SPARSE
        return layout.sparse and (
            sparse_changed or content not in old.sparse or content in old.mismatched(layout)
        )

    async def encode(self, point_ids: list[str]) -> dict[str, dict[str, SparseVec]]:
        """
        The re-encoded content sparse vector of each point, keyed for ``QdrantStoreCopyApi``.

        Args:
            point_ids (list[str]): The copied batch's point ids (each a chunk id).

        Returns:
            dict[str, dict[str, SparseVec]]: ``point id → {content_bm25: vector}`` (a text the
                provider maps to no term gets no vector).
        """
        # 1. The batch's chunk texts, then the sparse slot in provider-sized calls.
        pairs = await self.__texts(point_ids)
        encoded: dict[str, dict[str, SparseVec]] = {}
        for start in range(0, len(pairs), self._batch_size):
            window = pairs[start : start + self._batch_size]
            vectors = await self._embedder._embed_sparse([text for _, text in window]) or []
            # 2. Keep only non-empty vectors (Qdrant rejects an empty sparse vector).
            for (point_id, _), vector in zip(window, vectors, strict=True):
                if vector.indices:
                    encoded[point_id] = {
                        VectorNames.CONTENT_SPARSE: SparseVec(
                            indices=list(vector.indices), values=list(vector.values)
                        )
                    }
        return encoded


__all__ = ["ContentSparseReencoder"]
