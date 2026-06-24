# ====== Code Summary ======
# Static helpers for Qdrant collection lifecycle management.
# Handles create/ensure and drop operations for named hybrid-vector collections.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    SparseVectorParams,
    VectorParams,
)

# ====== Internal Project Imports ======
# Single source of truth for content vector names — defined in field_index and reused here.
from common_libs.search.field_index import CONTENT_DENSE, CONTENT_SPARSE


class QdrantCollectionAdmin:
    """
    Static helpers for Qdrant collection lifecycle operations.

    Encapsulates create/ensure/drop logic for DocForge hybrid-vector collections.
    All methods take the live ``AsyncQdrantClient`` as an explicit argument so that
    this class carries no instance state of its own.
    """

    logger = loggerplusplus.bind(identifier="QdrantCollectionAdmin")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[return]
        """Block instantiation — this is a static-only class."""
        raise TypeError("QdrantCollectionAdmin is a static-only class and cannot be instantiated.")

    @classmethod
    async def ensure_collection(
        cls,
        client: AsyncQdrantClient,
        collection_name: str,
        dense_dim: int,
        field_dense_names: list[str] | None,
        field_sparse_names: list[str] | None,
        recreate: bool,
    ) -> None:
        """
        Create the Qdrant collection if it does not already exist.

        Configured for multi-field hybrid search (spec §7.2):
        - ``content_dense`` / ``content_bm25`` — always present (the chunk body).
        - one named dense vector per ``semantic`` metadata field (``meta_<field>_dense``).
        - one named sparse vector per ``lexical`` metadata field (``meta_<field>_bm25``).

        Qdrant fixes the vector schema at creation — changing the metadata schema requires a
        new pipeline_version + reindex (recreate=True), consistent with ADR-15.

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target Qdrant collection name.
            dense_dim (int): Dense vector dimension (1024 for BGE-M3).
            field_dense_names (list[str] | None): Per-field dense vector names to create.
            field_sparse_names (list[str] | None): Per-field sparse vector names to create.
            recreate (bool): Drop and recreate if the collection already exists.
        """
        # 1. Optionally drop existing collection before recreating
        if recreate and await client.collection_exists(collection_name):
            await client.delete_collection(collection_name)
            cls.logger.info(f"Qdrant: dropped collection {collection_name!r} for recreation.")

        # 2. Create collection if absent — content vectors + one per metadata field
        if not await client.collection_exists(collection_name):
            vectors_config = {
                CONTENT_DENSE: VectorParams(size=dense_dim, distance=Distance.COSINE, on_disk=True),
            }
            for vname in field_dense_names or []:
                vectors_config[vname] = VectorParams(size=dense_dim, distance=Distance.COSINE, on_disk=True)

            sparse_config = {CONTENT_SPARSE: SparseVectorParams()}
            for vname in field_sparse_names or []:
                sparse_config[vname] = SparseVectorParams()

            await client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                sparse_vectors_config=sparse_config,
            )
            cls.logger.info(
                f"Qdrant: created collection {collection_name!r} "
                f"(dense={len(vectors_config)} vectors, sparse={len(sparse_config)} vectors)"
            )
        else:
            cls.logger.debug(f"Qdrant: collection {collection_name!r} already exists.")

    @classmethod
    async def drop_collection(cls, client: AsyncQdrantClient, collection_name: str) -> bool:
        """
        Delete a Qdrant collection if it exists (idempotent).

        Args:
            client (AsyncQdrantClient): Live Qdrant client.
            collection_name (str): Target collection.

        Returns:
            bool: True if a collection was dropped, False if it did not exist.
        """
        # 1. Guard against non-existent collections
        if not await client.collection_exists(collection_name):
            return False

        # 2. Drop and log
        await client.delete_collection(collection_name)
        cls.logger.info(f"Qdrant: dropped collection {collection_name!r}")
        return True
