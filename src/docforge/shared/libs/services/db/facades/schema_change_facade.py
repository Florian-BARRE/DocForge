# ====== Code Summary ======
# SchemaChangeFacade — the store reads/writes around a metadata-schema change that are NOT the schema
# rows themselves: counting the stored values a removal would destroy (the dry-run "values_lost"), and
# the post-commit, best-effort Qdrant cleanup of a field that left the schema (its payload key + index
# and its meta vectors' data on every point). The cleanup is convergent — it also clears residue the
# schema no longer explains — so a cleanup that failed once is repaired by the next schema change.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi, MetadataValueApi
from shared_libs.services.db.qdrant import QdrantClient, QdrantFieldPurgeApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


@dataclass(slots=True)
class FieldPurgeOutcome:
    """
    What a departed-field cleanup cleared from the vector store.

    Attributes:
        payload_keys (list[str]): Payload keys deleted from every point.
        vector_names (list[str]): Named vectors whose data was deleted from every point.
    """

    payload_keys: list[str] = field(default_factory=list)
    vector_names: list[str] = field(default_factory=list)


class SchemaChangeFacade(LoggerClass):
    """Value-loss counting + departed-field Qdrant cleanup around a metadata-schema change."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The tabular truth (schema rows + metadata values).
            qdrant (QdrantClient): The vector store carrying the denormalised field footprint.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def count_field_values(
        self, collection_id: uuid.UUID, field_names: Collection[str]
    ) -> dict[str, int]:
        """
        Count the stored values (document + chunk scope rows) of the named fields of a collection.

        Args:
            collection_id (uuid.UUID): The collection owning the fields.
            field_names (Collection[str]): The field names to count (unknown names count 0).

        Returns:
            dict[str, int]: field name → stored value rows (every requested name present).
        """
        # 1. Nothing asked → no round trip.
        if not field_names:
            return {}
        # 2. Resolve names → ids on the collection's schema, then one grouped count per value table.
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
            ids = {row.field_name: row.id for row in schema if row.field_name in field_names}
            by_id = await MetadataValueApi.count_rows_by_field(session, list(ids.values()))
        return {name: by_id.get(ids[name], 0) if name in ids else 0 for name in field_names}

    async def purge_departed_fields(
        self, collection_id: uuid.UUID, departed: Collection[str]
    ) -> FieldPurgeOutcome:
        """
        Clear departed fields' payload keys / indexes / meta-vector data from every Qdrant point.

        Runs AFTER the schema commit (Qdrant is not transactional with Postgres). Convergent: beyond
        the explicit ``departed`` names it also clears any indexed payload key or meta vector the
        CURRENT schema does not own, so residue left by an earlier failed cleanup is healed here. A
        clean no-op when the collection has no Qdrant space yet (never ingested). Raises on a store
        error — the caller decides it is best-effort.

        Args:
            collection_id (uuid.UUID): The collection whose points are cleaned.
            departed (Collection[str]): Field names removed / renamed away by the change.

        Returns:
            FieldPurgeOutcome: The payload keys and vector names actually cleared.
        """
        # 1. No Qdrant space → nothing was ever denormalised.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await self._qdrant.raw.collection_exists(name):
            return FieldPurgeOutcome()

        # 2. Residue = the departed names + whatever the current schema no longer explains.
        async with self._postgres.session() as session:
            current = [
                row.field_name for row in await CollectionApi.get_schema(session, collection_id)
            ]
        payload_keys, indexed_keys, vectors = await QdrantFieldPurgeApi.residue(
            self._qdrant.raw, name, departed=departed, current=current
        )

        # 3. Clear it from every point (filter-based, one request per op).
        await QdrantFieldPurgeApi.purge(
            self._qdrant.raw,
            name,
            payload_keys=payload_keys,
            indexed_keys=indexed_keys,
            vector_names=vectors,
        )
        outcome = FieldPurgeOutcome(payload_keys=sorted(payload_keys), vector_names=sorted(vectors))
        if payload_keys or vectors:
            self.logger.info(
                f"Purged departed-field residue on {collection_id}: payload keys "
                f"{outcome.payload_keys}, vectors {outcome.vector_names}"
            )
        return outcome


__all__ = ["SchemaChangeFacade", "FieldPurgeOutcome"]
