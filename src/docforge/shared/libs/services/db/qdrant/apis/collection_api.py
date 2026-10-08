# ====== Code Summary ======
# QdrantCollectionApi — the collection-lifecycle operations of the vector store: create the Qdrant
# collection (named vectors derived from the metadata schema + TYPED payload indexes for the
# filterable fields) idempotently, RECONCILE an existing collection with an evolved schema (add the
# missing payload indexes live — additive, safe), and drop it. A filterable field is indexed by its
# type so that exact-match and range filters actually work (a number gets an INTEGER/FLOAT index,
# not KEYWORD). Named vectors CANNOT be added to a live collection (a Qdrant limitation), so a field
# that becomes semantic/lexical after first ingest is reported as missing (an index rebuild must
# recreate the collection to declare it), never silently added. The content axes and the sparse IDF
# modifier follow the embedder's config-derived VectorLayout: a required content vector the store
# lacks, or a sparse vector whose modifier disagrees with the configured sparse provider, is reported
# missing the same way (index rebuild required).

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence

# ====== Third-Party Library Imports ======
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout

# ====== Local Project Imports ======
from ..vectors import DOCUMENT_ID_KEY, DeclaredVectors, PayloadType, QdrantVectorSchema, VectorNames
from .alias_api import QdrantAliasApi

# The field label a missing CONTENT vector is reported under (the search target name of the body).
CONTENT_LABEL = "content"


class QdrantCollectionApi:
    """Static collection-lifecycle operations (ensure / drop) for the vector store."""

    CONTENT_LABEL = CONTENT_LABEL

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
        layout: VectorLayout | None = None,
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
            layout (VectorLayout | None): The embedder's config-derived layout (which content axes,
                and whether every sparse vector carries the IDF modifier). None = the legacy
                dense + sparse, no-IDF layout with no content check on an existing collection.

        Returns:
            set[str]: The fields (``content`` for a content vector) whose named vector is missing or
                mismatched on an existing collection (reindex-required); empty for a fresh one.
        """
        # 1. Already provisioned → reconcile additively (never re-create, never a destructive op).
        if await QdrantAliasApi.resolve_or_adopt(client, name):
            return await cls.reconcile(
                client,
                name,
                semantic_fields=semantic_fields,
                lexical_fields=lexical_fields,
                filterable_fields=filterable_fields,
                layout=layout,
            )
        # 2. The vector space mirrors the contract AND the embedder's layout (no dense provider →
        #    no dense vector; the IDF modifier on every sparse vector iff the provider needs it).
        vectors_config = QdrantVectorSchema.dense_config(dense_dim, semantic_fields, layout)
        try:
            await client.create_collection(
                collection_name=name,
                vectors_config=vectors_config,
                sparse_vectors_config=QdrantVectorSchema.sparse_config(lexical_fields, layout),
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
        layout: VectorLayout | None = None,
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
            layout (VectorLayout | None): The embedder's config-derived layout (see ``ensure``).

        Returns:
            set[str]: Fields (``content`` for a content vector) whose named vector is missing or
                mismatched and cannot be fixed live (the collection must be reindexed).
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
        declared = await cls.declared(client, name)
        missing = cls.missing_vectors(
            semantic_fields,
            lexical_fields,
            set(declared.dense),
            set(declared.sparse),
            layout=layout,
            mismatched=declared.mismatched(layout) if layout is not None else frozenset(),
        )
        return {field_name for field_name, _ in missing}

    @staticmethod
    def missing_vectors(
        semantic_fields: Sequence[str],
        lexical_fields: Sequence[str],
        declared_dense: set[str],
        declared_sparse: set[str],
        *,
        layout: VectorLayout | None = None,
        mismatched: frozenset[str] | set[str] = frozenset(),
    ) -> list[tuple[str, str]]:
        """
        Pair every semantic/lexical field with the named vector it needs but Qdrant does not declare.

        Pure — the single rule shared by ``reconcile`` and the collection read surface (detail
        ``missing_vectors`` + PATCH ``reindex_required_fields``), so both compute the gap one way.

        Args:
            semantic_fields (Sequence[str]): Fields expected to carry a named dense vector.
            lexical_fields (Sequence[str]): Fields expected to carry a named sparse vector.
            declared_dense (set[str]): The dense vector names the collection declares.
            declared_sparse (set[str]): The sparse vector names the collection declares.
            layout (VectorLayout | None): The embedder's config-derived layout. When given, the
                content vectors of each configured axis are required too, a semantic field needs a
                dense provider and a lexical field a sparse one (else it is not indexable at all and
                not reported). None = the field-only legacy rule (both axes assumed).
            mismatched (set[str]): Declared sparse vectors whose IDF modifier disagrees with the
                layout — a REQUIRED one counts as missing (it holds another encoder's vectors).

        Returns:
            list[tuple[str, str]]: ``(field_name, vector_name)`` per missing vector, sorted
                (``content`` labels a content vector).
        """
        # 1. Which axes the embedder produces (legacy: both).
        dense_on = layout is None or layout.dense
        sparse_on = layout is None or layout.sparse
        required_dense = (
            [(f, VectorNames.field_dense(f)) for f in semantic_fields] if dense_on else []
        )
        required_sparse = (
            [(f, VectorNames.field_sparse(f)) for f in lexical_fields] if sparse_on else []
        )
        # 2. The content vectors are required only against an explicit layout.
        if layout is not None and layout.dense:
            required_dense.append((CONTENT_LABEL, VectorNames.CONTENT_DENSE))
        if layout is not None and layout.sparse:
            required_sparse.append((CONTENT_LABEL, VectorNames.CONTENT_SPARSE))
        # 3. Missing = undeclared, or (sparse) declared under the wrong modifier.
        missing = [pair for pair in required_dense if pair[1] not in declared_dense]
        missing += [
            pair
            for pair in required_sparse
            if pair[1] not in declared_sparse or pair[1] in mismatched
        ]
        return sorted(missing)

    @staticmethod
    async def declared(client: AsyncQdrantClient, name: str) -> DeclaredVectors:
        """
        Return what an existing collection declares (named vectors + IDF-declared sparse ones).

        Args:
            client (AsyncQdrantClient): The connection from QdrantClient.raw.
            name (str): The Qdrant collection name.

        Returns:
            DeclaredVectors: Empty when the collection does not exist.
        """
        if not await QdrantAliasApi.resolve_or_adopt(client, name):
            return DeclaredVectors()
        return DeclaredVectors.from_params((await client.get_collection(name)).config.params)

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
        # A missing collection declares nothing — never raise, just report emptiness.
        return (await QdrantCollectionApi.declared(client, name)).pair()

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
        if not await QdrantAliasApi.resolve_or_adopt(client, name):
            return 0
        # 2. An exact count of every point (unfiltered — the raw index size).
        return (await client.count(collection_name=name, exact=True)).count

    @staticmethod
    async def drop(client: AsyncQdrantClient, name: str) -> None:
        """Delete the whole Qdrant collection — alias-aware (deleting an alias name is a no-op in
        Qdrant, so the physical collection behind it, and any rebuild leftover, is deleted instead)."""
        await QdrantAliasApi.drop_all(client, name)


__all__ = ["QdrantCollectionApi"]
