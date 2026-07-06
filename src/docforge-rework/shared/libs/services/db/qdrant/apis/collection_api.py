# ====== Code Summary ======
# QdrantCollectionApi — the collection-lifecycle operations of the vector store: create the Qdrant
# collection (named vectors derived from the metadata schema + TYPED payload indexes for the
# filterable fields) idempotently, and drop it. A filterable field is indexed by its type so that
# exact-match and range filters actually work (a number gets an INTEGER/FLOAT index, not KEYWORD).

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models

# ====== Local Project Imports ======
from ..vectors import PayloadType, QdrantVectorSchema


class QdrantCollectionApi:
    """Static collection-lifecycle operations (ensure / drop) for the vector store."""

    # A filterable field's type → its Qdrant payload index schema.
    _PAYLOAD_SCHEMA: dict[PayloadType, models.PayloadSchemaType] = {
        PayloadType.KEYWORD: models.PayloadSchemaType.KEYWORD,
        PayloadType.INTEGER: models.PayloadSchemaType.INTEGER,
        PayloadType.FLOAT: models.PayloadSchemaType.FLOAT,
        PayloadType.BOOL: models.PayloadSchemaType.BOOL,
        PayloadType.DATETIME: models.PayloadSchemaType.DATETIME,
        PayloadType.TEXT: models.PayloadSchemaType.TEXT,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("QdrantCollectionApi is a static-only class and cannot be instantiated.")

    @classmethod
    async def ensure(
        cls,
        client: AsyncQdrantClient,
        name: str,
        *,
        dense_dim: int,
        semantic_fields: Sequence[str] = (),
        lexical_fields: Sequence[str] = (),
        filterable_fields: Mapping[str, PayloadType] | None = None,
    ) -> None:
        """
        Create the Qdrant collection (named vectors + typed payload indexes) if it does not exist.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (one per DocForge collection).
            dense_dim (int): Dimension of the dense vectors (e.g. 1024 for BGE-M3).
            semantic_fields (Sequence[str]): Fields that get a named dense vector.
            lexical_fields (Sequence[str]): Fields that get a named sparse (BM25) vector.
            filterable_fields (Mapping[str, PayloadType]): Filterable field → its index type.
        """
        # 1. Idempotent — created once, reused across every ingest into the collection.
        if await client.collection_exists(name):
            return
        # 2. The vector space mirrors the contract (content + per-field dense/sparse).
        await client.create_collection(
            collection_name=name,
            vectors_config=QdrantVectorSchema.dense_config(dense_dim, semantic_fields),
            sparse_vectors_config=QdrantVectorSchema.sparse_config(lexical_fields),
        )
        # 3. A typed payload index per filterable field, so exact/range filters work.
        for field_name, payload_type in (filterable_fields or {}).items():
            await client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=cls._PAYLOAD_SCHEMA[payload_type],
            )
        # 4. document_id is always indexed (keyword) for delete-by-document and document filters.
        await client.create_payload_index(
            collection_name=name,
            field_name="document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    @staticmethod
    async def drop(client: AsyncQdrantClient, name: str) -> None:
        """Delete the whole Qdrant collection if it exists."""
        if await client.collection_exists(name):
            await client.delete_collection(name)


__all__ = ["QdrantCollectionApi"]
