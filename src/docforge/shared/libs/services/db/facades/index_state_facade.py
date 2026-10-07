# ====== Code Summary ======
# IndexStateFacade — the READ view of what a collection's Qdrant store actually declares, versus what
# its metadata schema asks for. Qdrant cannot add a named vector to a live collection, so a field made
# semantic/lexical after first ingest stays without its vector until the index is rebuilt: Postgres
# flags alone are NOT the truth of what is searchable. The search target gate, the collection detail
# (``missing_vectors``) and the PATCH response (``reindex_required_fields``) all read this one view.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from qdrant_client.http.exceptions import UnexpectedResponse

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import QdrantClient, QdrantCollectionApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers

# Qdrant answers a lookup on an unknown collection with this status.
_NOT_FOUND = 404


class IndexStateFacade(LoggerClass):
    """Read the vectors a collection's Qdrant store declares and what its schema is missing."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The schema truth (semantic/lexical flags).
            qdrant (QdrantClient): The vector store whose declared named vectors are read.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def declared_vectors(self, collection_id: uuid.UUID) -> tuple[set[str], set[str]] | None:
        """
        Return the (dense, sparse) named vectors the collection's Qdrant store declares.

        ONE Qdrant round-trip (a 404 means "no space yet") — cheap enough to run per search request.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.

        Returns:
            tuple[set[str], set[str]] | None: The declared (dense, sparse) names, or None when the
                collection has no Qdrant space yet (never ingested — nothing is declared nor missing).
        """
        # 1. A missing collection is a 404 — report "no space" instead of raising.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        try:
            info = await self._qdrant.raw.get_collection(name)
        except UnexpectedResponse as error:
            if error.status_code == _NOT_FOUND:
                return None
            raise
        # 2. DocForge always uses NAMED vectors, so params.vectors is a name → params mapping.
        params = info.config.params
        dense = set(params.vectors.keys()) if isinstance(params.vectors, dict) else set()
        sparse = set(params.sparse_vectors.keys()) if params.sparse_vectors else set()
        return dense, sparse

    async def missing_for(
        self,
        collection_id: uuid.UUID,
        semantic_fields: Sequence[str],
        lexical_fields: Sequence[str],
    ) -> list[tuple[str, str]]:
        """
        Return the ``(field, vector)`` pairs a given searchable surface needs but the store lacks.

        Used directly for a dry-run PATCH (the TARGET schema is not stored yet) and by ``missing``.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.
            semantic_fields (Sequence[str]): Fields expected to carry a named dense vector.
            lexical_fields (Sequence[str]): Fields expected to carry a named sparse vector.

        Returns:
            list[tuple[str, str]]: Sorted missing pairs; empty when the collection has no space yet
                (its first ingest creates the full schema).
        """
        # 1. No space yet → the first ingest declares everything from the then-current schema.
        declared = await self.declared_vectors(collection_id)
        if declared is None:
            return []
        # 2. The shared pure rule (also used by reconcile).
        return QdrantCollectionApi.missing_vectors(
            semantic_fields, lexical_fields, declared[0], declared[1]
        )

    async def missing(self, collection_id: uuid.UUID) -> list[tuple[str, str]]:
        """
        Return the ``(field, vector)`` pairs the STORED schema needs but the Qdrant store lacks.

        Args:
            collection_id (uuid.UUID): The collection whose store is compared to its schema.

        Returns:
            list[tuple[str, str]]: Sorted missing pairs (empty when aligned or never ingested).
        """
        # 1. The searchable surface of the stored schema, then the shared comparison.
        async with self._postgres.session() as session:
            schema = await CollectionApi.get_schema(session, collection_id)
        return await self.missing_for(
            collection_id,
            [row.field_name for row in schema if row.semantic],
            [row.field_name for row in schema if row.lexical],
        )


__all__ = ["IndexStateFacade"]
