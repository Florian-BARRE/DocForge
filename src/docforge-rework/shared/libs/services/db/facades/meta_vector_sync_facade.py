# ====== Code Summary ======
# MetaVectorSyncFacade — populates a document's DOCUMENT-SCOPE metadata NAMED VECTORS (semantic dense
# + lexical sparse) on every one of its chunk Qdrant points, so a metadata-only search resolves to a
# vector that actually holds data. The value lives once per document in Postgres; a document-scope
# value is uniform, so the SAME meta vector rides on all the document's chunk points. Mirrors
# FilterSyncFacade but writes VECTORS (update_vectors) instead of payload scalars: it rebuilds the
# collection's OWN embedder from its ingestion blob and embeds only the short metadata VALUES — never
# the content. Idempotent, non-destructive (content vectors untouched), a clean no-op when the
# document has no indexed chunk or no semantic/lexical value. The write-side hook and the
# collection-wide backfill both go through the SAME per-document sync.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.base import BaseEmbedderNode
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, CollectionApi, DocumentApi
from shared_libs.services.db.qdrant import (
    QdrantClient,
    QdrantCollectionApi,
    QdrantIndexApi,
    QdrantPoint,
    SparseVec,
    VectorNames,
)

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .meta_vector_sync_helpers import MetaVectorSyncHelpers


class MetaVectorSyncFacade(LoggerClass):
    """Populate document-scope metadata named vectors (dense/sparse) onto every chunk's point."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (metadata values + embedder blob + flags).
            qdrant (QdrantClient): The vector store whose named meta vectors are populated.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def __build_meta_vectors(
        self,
        embedder: BaseEmbedderNode,
        rows: list[tuple[str, Any, bool, bool]],
        declared_dense: set[str],
        declared_sparse: set[str],
    ) -> tuple[dict[str, list[float]], dict[str, SparseVec]]:
        """Embed each field's value into its DECLARED named vector (dense semantic / sparse lexical)."""
        dense: dict[str, list[float]] = {}
        sparse: dict[str, SparseVec] = {}
        for field_name, value, semantic, lexical in rows:
            # 1. Empty values carry no vector (mirrors the embed node's skip).
            text = MetaVectorSyncHelpers.render_value(value)
            if text is None:
                continue
            # 2. Semantic → the dense meta vector, only when the collection declares it.
            if semantic:
                await self.__add_dense(embedder, field_name, text, declared_dense, dense)
            # 3. Lexical → the sparse meta vector, only when both the collection AND the embedder
            #    carry the axis (a dense-only embedder simply skips it, loudly).
            if lexical:
                await self.__add_sparse(embedder, field_name, text, declared_sparse, sparse)
        return dense, sparse

    async def __add_dense(
        self,
        embedder: BaseEmbedderNode,
        field_name: str,
        text: str,
        declared_dense: set[str],
        dense: dict[str, list[float]],
    ) -> None:
        """Embed a semantic field's value into its dense meta vector (declared-guarded)."""
        vector_name = VectorNames.field_dense(field_name)
        if vector_name not in declared_dense:
            self.logger.warning(
                f"Dense meta vector '{vector_name}' not declared on collection — skipped"
            )
            return
        dense[vector_name] = (await embedder._embed_dense([text]))[0]

    async def __add_sparse(
        self,
        embedder: BaseEmbedderNode,
        field_name: str,
        text: str,
        declared_sparse: set[str],
        sparse: dict[str, SparseVec],
    ) -> None:
        """Embed a lexical field's value into its sparse meta vector (declared + axis guarded)."""
        vector_name = VectorNames.field_sparse(field_name)
        if vector_name not in declared_sparse:
            self.logger.warning(
                f"Sparse meta vector '{vector_name}' not declared on collection — skipped"
            )
            return
        vectors = await embedder._embed_sparse([text])
        if not vectors:
            self.logger.warning(
                f"Embedder has no sparse axis — lexical vector '{vector_name}' skipped"
            )
            return
        sparse[vector_name] = SparseVec(indices=vectors[0].indices, values=vectors[0].values)

    async def sync_document_meta_vectors(self, document_id: uuid.UUID) -> int:
        """
        Populate a document's semantic/lexical document-scope metadata vectors on all its points.

        The values are read once from Postgres, embedded with the collection's OWN embedder, and
        written (a partial named-vector update) onto every indexed chunk point — a document-scope
        value is uniform, so the same meta vector rides every chunk. Never re-embeds content;
        re-running yields the same vectors (idempotent). Skips cleanly when the document has no
        indexed chunk or no semantic/lexical value.

        Args:
            document_id (uuid.UUID): The document to synchronise.

        Returns:
            int: The number of chunk points patched (0 when there is nothing to embed or to carry).
        """
        # 1. Read the document, its collection (embedder blob), its searchable values + point ids.
        async with self._postgres.session() as session:
            document = await DocumentApi.get(session, document_id)
            if document is None:
                return 0
            collection = await CollectionApi.get(session, document.collection_id)
            if collection is None:
                return 0
            rows = await DocumentApi.get_searchable_metadata(session, document_id)
            chunk_ids = await ChunkApi.get_indexed_ids_for_document(session, document_id)

        # 2. No value to embed, or no point to carry it → clean no-op.
        if not rows or not chunk_ids:
            return 0

        # 3. Rebuild the embedder from the collection's ingestion blob (drifted blob fails loudly).
        embed_node = MetaVectorSyncHelpers.find_embed_node(collection.pipeline)
        if embed_node is None:
            self.logger.warning(
                f"Collection {document.collection_id} has no embed node — meta vectors skipped"
            )
            return 0
        embedder, _config = MetaVectorSyncHelpers.rebuild_embedder(embed_node)

        # 4. Embed each value into its DECLARED named meta vector (guarded against undeclared names).
        name = DatabaseHelpers.qdrant_collection_name(document.collection_id)
        declared_dense, declared_sparse = await QdrantCollectionApi.declared_vectors(
            self._qdrant.raw, name
        )
        dense, sparse = await self.__build_meta_vectors(
            embedder, rows, declared_dense, declared_sparse
        )
        if not dense and not sparse:
            return 0

        # 5. The SAME meta vectors on every chunk point (partial update — content vectors untouched).
        points = [
            QdrantPoint(point_id=str(chunk_id), payload={}, dense=dict(dense), sparse=dict(sparse))
            for chunk_id in chunk_ids
        ]
        await QdrantIndexApi.update_vectors(self._qdrant.raw, name, points)
        self.logger.info(
            f"Synced {len(dense)} dense + {len(sparse)} sparse meta vector(s) onto "
            f"{len(chunk_ids)} point(s) for document {document_id}"
        )
        return len(chunk_ids)

    async def backfill_collection_meta_vectors(
        self, collection_id: uuid.UUID
    ) -> tuple[int, int]:
        """
        Run the per-document meta-vector sync across every document of a collection (one-off backfill).

        The maintenance path for data ingested before the meta vectors were populated: no content
        re-embed, only the short metadata values embedded and written per document. Idempotent.

        Args:
            collection_id (uuid.UUID): The collection whose documents are backfilled.

        Returns:
            tuple[int, int]: (documents that received meta vectors, total points patched).
        """
        # 1. Every document of the collection gets the same per-document sync.
        async with self._postgres.session() as session:
            documents = await DocumentApi.list_for_collection(session, collection_id)

        # 2. Accumulate what was actually patched (documents with values AND indexed chunks).
        documents_synced = 0
        points_patched = 0
        for document in documents:
            patched = await self.sync_document_meta_vectors(document.id)
            if patched:
                documents_synced += 1
                points_patched += patched

        self.logger.info(
            f"Backfilled meta vectors on collection {collection_id}: "
            f"{documents_synced} document(s), {points_patched} point(s)"
        )
        return documents_synced, points_patched


__all__ = ["MetaVectorSyncFacade"]
