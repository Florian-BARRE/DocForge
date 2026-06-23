# ====== Code Summary ======
# MetadataIndexerHelpers — static helpers extracted from MetadataIndexer to keep
# metadata_indexer.py under 200 lines.
#
# Covers: per-field vector sync (_sync_field logic) and field-value normalization
# (_value logic).  All methods accept the embed provider and Qdrant client as
# explicit arguments so they remain stateless pure helpers.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.providers.embed.tei import TeiEmbedProvider
    from libs.storage.qdrant.client import QdrantStorageClient

# ====== Internal Project Imports ======
from libs.search.field_index import FieldIndexHelpers


class MetadataIndexerHelpers:
    """
    Static helpers for MetadataIndexer.

    Groups the per-field vector sync and field-value normalization utilities.
    All methods accept the embed provider and Qdrant client as explicit arguments
    so no instance state is required.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("MetadataIndexerHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    async def sync_field(
        embed: TeiEmbedProvider,
        qdrant: QdrantStorageClient,
        collection_name: str,
        point_ids: list[str],
        field: Any,
        name: str,
        value: str | None,
        summary: dict[str, Any],
    ) -> None:
        """
        Re-embed (or clear) the per-field dense/sparse vectors for one changed field.

        Args:
            embed (TeiEmbedProvider): BGE-M3 TEI provider (dense + sparse).
            qdrant (QdrantStorageClient): Connected Qdrant client.
            collection_name (str): Qdrant collection name.
            point_ids (list[str]): All point ids belonging to the document.
            field (Any): The schema field object (ORM row or dict).
            name (str): Field name as stored in the schema.
            value (str | None): New field value; None means the field was cleared.
            summary (dict): Mutable summary dict updated in place with vector changes.

        Returns:
            None
        """
        semantic = FieldIndexHelpers._attr(field, "semantic", False)
        lexical = FieldIndexHelpers._attr(field, "lexical", False)
        if not (semantic or lexical):
            return

        # 1. Cleared field → drop its named vectors
        if value is None:
            names = ([FieldIndexHelpers.field_dense_name(name)] if semantic else []) + (
                [FieldIndexHelpers.field_sparse_name(name)] if lexical else []
            )
            await qdrant.delete_points_named_vectors(collection_name, point_ids, names)
            summary["vectors_deleted"].extend(names)
            return

        # 2. Re-embed the new value once (dense + sparse from a single TEI call)
        result = await embed.embed([value])
        dense_vec = result.vectors[0] if result.vectors else None
        sparse_map = result.sparse[0] if result.sparse else None

        # 3. Broadcast the new vector to every point of the document
        if semantic and dense_vec is not None:
            vname = FieldIndexHelpers.field_dense_name(name)
            await qdrant.update_points_named_vector(collection_name, point_ids, vname, dense=dense_vec)
            summary["vectors_updated"].append(vname)
        if lexical and sparse_map:
            vname = FieldIndexHelpers.field_sparse_name(name)
            await qdrant.update_points_named_vector(collection_name, point_ids, vname, sparse=sparse_map)
            summary["vectors_updated"].append(vname)

    @staticmethod
    def value(doc_meta: dict[str, Any], name: str) -> str | None:
        """
        Normalize a document-level field value to text (mirrors resolve_field_text).

        Args:
            doc_meta (dict): The document's merged metadata dict.
            name (str): Field name to look up.

        Returns:
            str | None: The field value cast to str, or None if absent or empty string.
        """
        raw = doc_meta.get(name)
        return None if raw is None or raw == "" else str(raw)
