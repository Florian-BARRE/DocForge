# ====== Code Summary ======
# QdrantCollectionApi — the collection-lifecycle operations of the vector store: create the Qdrant
# collection (named vectors derived from the metadata schema + TYPED payload indexes for the
# filterable fields) idempotently, RECONCILE an existing collection with an evolved schema (add the
# missing payload indexes live — additive, safe), and drop it. A filterable field is indexed by its
# type so that exact-match and range filters actually work (a number gets an INTEGER/FLOAT index,
# not KEYWORD). Named vectors CANNOT be added to a live collection (a Qdrant limitation), so a field
# that becomes semantic/lexical after first ingest is reported as reindex-required, not silently added.

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

# ====== Local Project Imports ======
from ..vectors import DOCUMENT_ID_KEY, PayloadType, QdrantVectorSchema, VectorNames


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
    ) -> set[str]:
        """
        Create the Qdrant collection if it does not exist, else RECONCILE it with the schema.

        Idempotent and additive in both branches: a fresh collection is built with the full named-
        vector space + typed payload indexes; an existing one has its MISSING payload indexes added
        live (a field toggled ``filterable`` after first ingest becomes queryable without a reindex).

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (one per DocForge collection).
            dense_dim (int): Dimension of the dense vectors (e.g. 1024 for BGE-M3).
            semantic_fields (Sequence[str]): Fields that get a named dense vector.
            lexical_fields (Sequence[str]): Fields that get a named sparse (BM25) vector.
            filterable_fields (Mapping[str, PayloadType]): Filterable field → its index type.

        Returns:
            set[str]: The semantic/lexical fields whose named vector is missing on an existing
                collection (reindex-required); always empty for a fresh collection.
        """
        # 1. Already provisioned → reconcile additively (never re-create, never a destructive op).
        if await client.collection_exists(name):
            return await cls.reconcile(
                client,
                name,
                semantic_fields=semantic_fields,
                lexical_fields=lexical_fields,
                filterable_fields=filterable_fields,
            )
        # 2. The vector space mirrors the contract (content + per-field dense).
        vectors_config = QdrantVectorSchema.dense_config(dense_dim, semantic_fields)
        try:
            await client.create_collection(
                collection_name=name,
                vectors_config=vectors_config,
                sparse_vectors_config=QdrantVectorSchema.sparse_config(lexical_fields),
            )
        except UnexpectedResponse as error:
            # collection_exists()→create is NOT atomic: when several documents ingest concurrently
            # into a BRAND-NEW collection, two workers can both see "missing" and both create, and
            # the loser gets 409 "already exists". That is success, not failure — the winner builds
            # the same space + indexes; a 409 here must never fail an ingest. Any other status re-raises.
            if error.status_code == 409:
                return set()
            raise
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
            field_name=DOCUMENT_ID_KEY,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        return set()

    @classmethod
    async def reconcile(
        cls,
        client: AsyncQdrantClient,
        name: str,
        *,
        semantic_fields: Sequence[str] = (),
        lexical_fields: Sequence[str] = (),
        filterable_fields: Mapping[str, PayloadType] | None = None,
    ) -> set[str]:
        """
        Additively align an EXISTING collection with an evolved schema — no destructive op.

        Adds only the payload indexes the collection is missing (idempotent: an index already present
        is left as-is) so a field toggled ``filterable`` after first ingest gains its index live.
        Named vectors cannot be added to a live Qdrant collection, so a field that became
        semantic/lexical without a declared vector is reported for a reindex rather than silently
        dropped (which would name a vector search never finds — a hard search error).

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name (must already exist — the caller guards this).
            semantic_fields (Sequence[str]): Fields expected to carry a named dense vector.
            lexical_fields (Sequence[str]): Fields expected to carry a named sparse vector.
            filterable_fields (Mapping[str, PayloadType]): Filterable field → its index type.

        Returns:
            set[str]: Fields whose semantic/lexical named vector is missing and cannot be added live
                (the collection must be reindexed to make them searchable).
        """
        # 1. The payload indexes already on the collection — only the missing ones are created.
        info = await client.get_collection(name)
        existing_indexes = set((info.payload_schema or {}).keys())
        for field_name, payload_type in (filterable_fields or {}).items():
            if field_name not in existing_indexes:
                await client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=cls._PAYLOAD_SCHEMA[payload_type],
                )
        # 2. document_id is always indexed — add it if a legacy collection somehow lacks it.
        if DOCUMENT_ID_KEY not in existing_indexes:
            await client.create_payload_index(
                collection_name=name,
                field_name=DOCUMENT_ID_KEY,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        # 3. Named vectors can't be added live — report the ones the schema wants but Qdrant lacks.
        declared_dense, declared_sparse = await cls.declared_vectors(client, name)
        reindex_fields: set[str] = set()
        for field_name in semantic_fields:
            if VectorNames.field_dense(field_name) not in declared_dense:
                reindex_fields.add(field_name)
        for field_name in lexical_fields:
            if VectorNames.field_sparse(field_name) not in declared_sparse:
                reindex_fields.add(field_name)
        return reindex_fields

    @staticmethod
    async def declared_vectors(client: AsyncQdrantClient, name: str) -> tuple[set[str], set[str]]:
        """
        Return the (dense, sparse) named vectors declared on an existing collection.

        The read guard for post-hoc vector writes: a named vector cannot be added to a live Qdrant
        collection without a reindex, so writing an undeclared vector errors. A caller checks its
        target names against these sets before calling ``update_vectors``.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.

        Returns:
            tuple[set[str], set[str]]: (declared dense vector names, declared sparse vector names).
                Both empty when the collection does not exist.
        """
        # 1. A missing collection declares nothing — never raise, just report emptiness.
        if not await client.collection_exists(name):
            return set(), set()
        # 2. DocForge always uses NAMED vectors, so params.vectors is a name → params mapping.
        params = (await client.get_collection(name)).config.params
        dense = set(params.vectors.keys()) if isinstance(params.vectors, dict) else set()
        sparse = set(params.sparse_vectors.keys()) if params.sparse_vectors else set()
        return dense, sparse

    @staticmethod
    async def count(client: AsyncQdrantClient, name: str) -> int:
        """
        Return the number of points stored in a collection (0 when it does not exist yet).

        A collection provisions its Qdrant space lazily at first indexing, so a created-but-never
        ingested collection has no space to count — that is reported as 0, never a 404. The count is
        unfiltered (every point, enabled or not): it is the raw index size the health surface shows.

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.

        Returns:
            int: The point count, or 0 when the collection has no Qdrant space yet.
        """
        # 1. No space provisioned yet — nothing indexed, report 0 rather than raising.
        if not await client.collection_exists(name):
            return 0
        # 2. An exact count of every point (unfiltered — the raw index size).
        return (await client.count(collection_name=name, exact=True)).count

    @staticmethod
    async def drop(client: AsyncQdrantClient, name: str) -> None:
        """Delete the whole Qdrant collection if it exists."""
        if await client.collection_exists(name):
            await client.delete_collection(name)


__all__ = ["QdrantCollectionApi"]
