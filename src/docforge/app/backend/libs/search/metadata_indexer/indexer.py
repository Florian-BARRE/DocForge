# ====== Code Summary ======
# MetadataIndexer — propagates a document-level metadata change to the live Qdrant index
# WITHOUT a full pipeline re-run.  For each changed field it patches the filter payload, and —
# only when the field is searchable — re-embeds just that value into its per-field vector
# (dense for `semantic`, sparse/BM25 for `lexical`), exactly as the collection config dictates.
# Document-level fields embed to the same value for every chunk, so one embedding is broadcast
# across the document's points.
#
# Per-field sync and value normalization are delegated to MetadataIndexerHelpers
# (helpers.py) to keep this file under 200 lines.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from common_libs.pipeline.bricks.providers.embed import TeiEmbedProvider
from common_libs.search.field_index import (
    CONTENT_DENSE,
    CONTENT_SPARSE,
    FieldIndexHelpers,
)
from common_libs.storage.postgres.repositories.chunk_repo import ChunkRepository
from common_libs.storage.qdrant.client import QdrantStorageClient

# ====== Local Project Imports ======
from .helpers import MetadataIndexerHelpers


class MetadataIndexer(LoggerClass):
    """
    Surgically syncs a document's indexed vectors/payload after a metadata edit.

    Only the changed fields are touched: filterable fields update the Qdrant payload; semantic
    fields re-embed into ``meta_<field>_dense``; lexical fields re-embed into ``meta_<field>_bm25``.
    Cleared fields have their payload key and per-field vectors removed.
    """

    def __init__(
        self,
        embed_provider: TeiEmbedProvider,
        qdrant: QdrantStorageClient,
        chunk_repo: ChunkRepository,
    ) -> None:
        """
        Initialize the indexer with the same embed + Qdrant clients used by S6/retrieval.

        Args:
            embed_provider (TeiEmbedProvider): BGE-M3 TEI provider (dense + sparse).
            qdrant (QdrantStorageClient): Connected Qdrant client.
            chunk_repo (ChunkRepository): Chunk repository (resolves a document's point ids).
        """
        LoggerClass.__init__(self)
        self._embed = embed_provider
        self._qdrant = qdrant
        self._chunk_repo = chunk_repo

    async def sync_document_fields(
        self,
        session: AsyncSession,
        *,
        collection_name: str,
        document_id: uuid.UUID,
        metadata_fields: list[Any],
        doc_meta: dict[str, Any],
        changed_field_names: set[str],
    ) -> dict[str, Any]:
        """
        Apply the changed metadata fields to the document's points in Qdrant.

        Args:
            session (AsyncSession): Active session (used to resolve the document's chunk ids).
            collection_name (str): Qdrant collection name (the collection id as a string).
            document_id (uuid.UUID): The document whose points are updated.
            metadata_fields (list): The collection's metadata schema (ORM rows or dicts).
            doc_meta (dict): The document's full field values after the edit.
            changed_field_names (set[str]): Field names whose value changed (added/edited/cleared).

        Returns:
            dict: Summary ``{n_points, payload_set, payload_removed, vectors_updated,
                vectors_deleted}`` describing exactly what was synced.
        """
        # 1. Resolve the document's point ids (point id == chunk id)
        chunks = await self._chunk_repo.get_by_document(session, document_id)
        point_ids = [str(c["id"]) for c in chunks]
        summary: dict[str, Any] = {
            "n_points": len(point_ids), "payload_set": [], "payload_removed": [],
            "vectors_updated": [], "vectors_deleted": [],
        }
        if not point_ids:
            return summary  # nothing indexed yet for this document

        # 2. Index the changed fields that exist in the schema
        schema = {FieldIndexHelpers._attr(f, "field_name"): f for f in metadata_fields}
        payload_set: dict[str, Any] = {}
        payload_remove: list[str] = []
        for name in changed_field_names:
            field = schema.get(name)
            if field is None:
                continue  # unknown field (kept by an "ignore" policy) — never indexed
            value = MetadataIndexerHelpers.value(doc_meta, name)
            await MetadataIndexerHelpers.sync_field(
                self._embed, self._qdrant, collection_name, point_ids, field, name, value, summary
            )
            # Collect payload changes for a single batched call
            if FieldIndexHelpers._attr(field, "filterable", False):
                (payload_set.__setitem__(name, value) if value is not None
                 else payload_remove.append(name))

        # 3. Apply payload patch + removals
        if payload_set:
            await self._qdrant.set_points_payload(collection_name, point_ids, payload_set)
            summary["payload_set"] = list(payload_set)
        if payload_remove:
            await self._qdrant.delete_points_payload_keys(collection_name, point_ids, payload_remove)
            summary["payload_removed"] = payload_remove

        self.logger.info(
            f"MetadataIndexer synced doc={document_id} points={len(point_ids)} "
            f"vectors_updated={summary['vectors_updated']} vectors_deleted={summary['vectors_deleted']}"
        )
        return summary

    async def reembed_content(
        self, collection_name: str, point_id: str, embed_text: str
    ) -> dict[str, Any]:
        """
        Re-embed a single chunk's content vectors after its text was manually corrected.

        Args:
            collection_name (str): Qdrant collection (the collection id as a string).
            point_id (str): The chunk id / Qdrant point id.
            embed_text (str): The new contextualized text to embed.

        Returns:
            dict: ``{"vectors_updated": [names]}``.
        """
        # 1. Embed the corrected text — produces both dense and sparse vectors in one call
        result = await self._embed.embed([embed_text])
        dense_vec = result.vectors[0] if result.vectors else None
        sparse_map = result.sparse[0] if result.sparse else None
        updated: list[str] = []

        # 2. Push the new dense content vector to Qdrant if available
        if dense_vec is not None:
            await self._qdrant.update_points_named_vector(
                collection_name, [point_id], CONTENT_DENSE, dense=dense_vec
            )
            updated.append(CONTENT_DENSE)

        # 3. Push the new sparse content vector to Qdrant if available
        if sparse_map:
            await self._qdrant.update_points_named_vector(
                collection_name, [point_id], CONTENT_SPARSE, sparse=sparse_map
            )
            updated.append(CONTENT_SPARSE)
        self.logger.info(f"Re-embedded content for point={point_id} vectors={updated}")
        return {"vectors_updated": updated}
