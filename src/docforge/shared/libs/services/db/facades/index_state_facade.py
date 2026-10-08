# ====== Code Summary ======
# IndexStateFacade — the READ view of what a collection's Qdrant store actually declares, versus what
# its metadata schema AND its embed config ask for. Qdrant cannot add a named vector to a live
# collection, so a field made semantic/lexical after first ingest stays without its vector until the
# index is rebuilt: Postgres flags alone are NOT the truth of what is searchable. The embed config
# adds two more requirements: the content vector of each configured axis (dense / sparse) and the
# sparse IDF modifier (a store whose sparse vectors were declared for another sparse provider holds
# another encoder's vectors — reported missing, rebuild required). The search target gate, the
# collection detail (``missing_vectors``) and the PATCH response (``reindex_required_fields``) all
# read this one view.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from qdrant_client.http.exceptions import UnexpectedResponse

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.embed.blob import EmbedBlobResolver
from shared_libs.public_models import VectorLayout
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import CollectionApi
from shared_libs.services.db.qdrant import (
    DeclaredVectors,
    QdrantAliasApi,
    QdrantClient,
    QdrantCollectionApi,
)

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers

# Qdrant answers a lookup on an unknown collection with this status.
_NOT_FOUND = 404


class IndexStateFacade(LoggerClass):
    """Read the vectors a collection's Qdrant store declares and what its schema/config is missing."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        """
        Args:
            postgres (PostgresClient): The schema + embed config truth.
            qdrant (QdrantClient): The vector store whose declared named vectors are read.
        """
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def declared(self, collection_id: uuid.UUID) -> DeclaredVectors | None:
        """
        Return what the collection's Qdrant store declares (named vectors + IDF-declared sparse).

        ONE Qdrant round-trip once the name resolves — cheap enough to run per search request. The
        alias read is the healing one: a stranded complete rebuild generation is adopted.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.

        Returns:
            DeclaredVectors | None: The declarations, or None when the collection has no Qdrant
                space yet (never ingested — nothing is declared nor missing).
        """
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if not await QdrantAliasApi.resolve_or_adopt(self._qdrant.raw, name):
            return None
        try:
            info = await self._qdrant.raw.get_collection(name)
        except UnexpectedResponse as error:  # dropped between the two calls
            if error.status_code == _NOT_FOUND:
                return None
            raise
        return DeclaredVectors.from_params(info.config.params)

    async def declared_vectors(self, collection_id: uuid.UUID) -> tuple[set[str], set[str]] | None:
        """
        Return the (dense, sparse) named vectors the collection's Qdrant store declares.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.

        Returns:
            tuple[set[str], set[str]] | None: The declared names, or None when no space exists yet.
        """
        declared = await self.declared(collection_id)
        return declared.pair() if declared is not None else None

    async def layout(self, collection_id: uuid.UUID) -> VectorLayout:
        """
        The vector layout the collection's STORED embed config dictates (default when unknown).

        Args:
            collection_id (uuid.UUID): The collection whose pipeline blob is read.

        Returns:
            VectorLayout: The config-derived layout (never read from the live store).
        """
        async with self._postgres.session() as session:
            collection = await CollectionApi.get(session, collection_id)
        return EmbedBlobResolver.layout(getattr(collection, "pipeline", None))

    async def missing_for(
        self,
        collection_id: uuid.UUID,
        semantic_fields: Sequence[str],
        lexical_fields: Sequence[str],
        layout: VectorLayout | None = None,
    ) -> list[tuple[str, str]]:
        """
        Return the ``(field, vector)`` pairs a given searchable surface needs but the store lacks.

        Used directly for a dry-run PATCH (the TARGET schema is not stored yet) and by ``missing``.

        Args:
            collection_id (uuid.UUID): The collection whose store is inspected.
            semantic_fields (Sequence[str]): Fields expected to carry a named dense vector.
            lexical_fields (Sequence[str]): Fields expected to carry a named sparse vector.
            layout (VectorLayout | None): The embed layout (None → read from the stored config).

        Returns:
            list[tuple[str, str]]: Sorted missing pairs (``content`` labels a content vector, a
                modifier-mismatched sparse vector counts as missing); empty when the collection has
                no space yet (its first ingest creates the full schema).
        """
        # 1. No space yet → the first ingest declares everything from the then-current config.
        declared = await self.declared(collection_id)
        if declared is None:
            return []
        # 2. The shared pure rule (also used by reconcile), against the config-derived layout.
        layout = layout or await self.layout(collection_id)
        return QdrantCollectionApi.missing_vectors(
            semantic_fields,
            lexical_fields,
            set(declared.dense),
            set(declared.sparse),
            layout=layout,
            mismatched=declared.mismatched(layout),
        )

    async def missing(self, collection_id: uuid.UUID) -> list[tuple[str, str]]:
        """
        Return the ``(field, vector)`` pairs the STORED schema + embed config need but the store lacks.

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
