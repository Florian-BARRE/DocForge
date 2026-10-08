# ====== Code Summary ======
# CollectionStoreReconciler — the store-side counterpart of a schema edit: additively align a
# collection's Qdrant space with its CURRENT metadata schema (a newly-filterable field gets its payload
# index live) and report the semantic/lexical fields whose named vector only a reindex can add.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import QdrantAliasApi, QdrantClient, QdrantCollectionApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class CollectionStoreReconciler(LoggerClass):
    """Idempotent, additive reconciliation of a collection's Qdrant space with its schema."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth the current schema is read from.
            qdrant (QdrantClient): The vector store aligned with that schema.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def reconcile_store(self, collection_id: uuid.UUID) -> set[str]:
        """
        Additively reconcile the Qdrant collection with the CURRENT metadata schema (idempotent).

        The store-side counterpart of a schema edit: a field toggled ``filterable`` after first
        ingest gets its payload index added LIVE (no reindex, no destructive op), so its search
        filter starts matching. A field toggled ``semantic``/``lexical`` needs a named vector, which
        Qdrant cannot add to a live collection — those are returned as reindex-required, never
        silently ignored. A no-op (empty set) when the collection has no Qdrant space yet: the first
        ingest provisions it from the current schema, so nothing is missing to reconcile.

        Args:
            collection_id (uuid.UUID): The collection whose vector store is reconciled.

        Returns:
            set[str]: Fields whose semantic/lexical named vector is missing and needs a reindex
                (empty when nothing is missing or the collection was never ingested).
        """
        # 1. No Qdrant space provisioned yet → the first ingest builds it from the schema; nothing
        #    to reconcile. Guard here so reconcile() can assume the collection exists.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await QdrantAliasApi.resolve_or_adopt(self._qdrant.raw, name):
            return set()
        # 2. Derive the searchable surface from the current schema and additively align the store.
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        reindex_fields = await QdrantCollectionApi.reconcile(
            self._qdrant.raw,
            name,
            semantic_fields=[f.field_name for f in schema if f.semantic],
            lexical_fields=[f.field_name for f in schema if f.lexical],
            filterable_fields={
                f.field_name: DatabaseHelpers.payload_type_for(f.field_type)
                for f in schema
                if f.filterable
            },
        )
        self.logger.info(
            f"Reconciled Qdrant store for {collection_id} "
            f"(reindex-required fields: {sorted(reindex_fields)})"
        )
        return reindex_fields


__all__ = ["CollectionStoreReconciler"]
