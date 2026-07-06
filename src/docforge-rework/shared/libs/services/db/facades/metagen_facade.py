# ====== Code Summary ======
# MetagenFacade — the POST-HOC metadata path: an LLM computed values for a generated field over
# EXISTING chunks, and they must land on both sides without re-ingesting anything. Postgres side:
# upsert into chunk_metadata (a re-run overwrites in place). Qdrant side: patch the payload
# (filterable values) and/or update the field's named vectors (semantic/lexical values) on the
# existing points. Idempotent: re-applying the same values is safe on both stores.

# ====== Standard Library Imports ======
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

# ====== Internal Project Imports ======
from loggerplusplus import LoggerClass

from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi
from shared_libs.services.db.postgresql.tables import ChunkMetadata
from shared_libs.services.db.qdrant import QdrantClient, QdrantIndexApi, QdrantPoint

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers


class MetagenFacade(LoggerClass):
    """Apply post-hoc generated chunk metadata to Postgres AND the Qdrant index."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    async def apply(
        self,
        collection_id: uuid.UUID,
        values: Sequence[ChunkMetadata],
        *,
        payload_patches: Mapping[str, dict[str, Any]] | None = None,
        vector_updates: Sequence[QdrantPoint] = (),
    ) -> None:
        """
        Persist generated chunk metadata and reflect it into the index — no re-ingest.

        The field MUST already be declared in the collection schema (its named vector exists from
        creation); the caller computes the vectors (embedding is the pipeline's job) and the
        payload patches for the filterable values.

        Args:
            collection_id (uuid.UUID): The collection the chunks belong to.
            values (Sequence[ChunkMetadata]): The generated values (upserted on chunk+field).
            payload_patches (Mapping | None): point id → payload keys to set (filterable fields).
            vector_updates (Sequence[QdrantPoint]): Named-vector updates (semantic/lexical fields).
        """
        # 1. The truth first (Postgres upsert — a re-run overwrites in place).
        async with self._postgres.session() as session:
            await ChunkApi.upsert_metadata(session, values)
        # 2. Then the index: payload for filtering, named vectors for searching.
        name = DatabaseHelpers.qdrant_collection_name(collection_id)
        if payload_patches:
            await QdrantIndexApi.set_payload(self._qdrant.raw, name, payload_patches)
        if vector_updates:
            await QdrantIndexApi.update_vectors(self._qdrant.raw, name, vector_updates)
        self.logger.info(
            f"Metagen applied on collection {collection_id}: {len(values)} values, "
            f"{len(payload_patches or {})} payload patches, {len(vector_updates)} vector updates"
        )


__all__ = ["MetagenFacade"]
