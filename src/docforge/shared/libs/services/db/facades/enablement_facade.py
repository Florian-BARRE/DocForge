# ====== Code Summary ======
# EnablementFacade — the reversible enable/disable (searchability) write surface. A toggle is a
# FLAG flip, never a re-embed: disabling a document is a single Postgres flag (search excludes its
# chunks with a bounded must_not, no Qdrant fan-out); toggling a chunk sets its enabled_override in
# Postgres and flips the `enabled` scalar on its EXISTING Qdrant point (set_payload), so the vector
# is untouched and the change is fully reversible. The one thing it will NOT do is fabricate a point
# for a never-embedded chunk: enabling one reports `reindex_required` for a later on-demand embed.

# ====== Standard Library Imports ======
import uuid
from collections import defaultdict
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from sqlalchemy.ext.asyncio import AsyncSession

# ====== Internal Project Imports ======
from shared_libs.public_models import ChunkRole, role_default_enabled
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, DocumentApi
from shared_libs.services.db.postgresql.tables import Chunk
from shared_libs.services.db.qdrant import ENABLED_KEY, QdrantClient, QdrantIndexApi

# ====== Local Project Imports ======
from .helpers import DatabaseHelpers
from .payloads import ChunkToggle


class EnablementFacade(LoggerClass):
    """Reversible enable/disable of documents and chunks (Postgres flag + Qdrant payload flip)."""

    def __init__(self, postgres: PostgresClient, qdrant: QdrantClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres
        self._qdrant = qdrant

    # -------------------- documents --------------------
    async def set_document_enabled(self, document_id: uuid.UUID, enabled: bool) -> bool:
        """
        Toggle a document's searchability — a pure Postgres flag (no Qdrant fan-out).

        Search excludes a disabled document's chunks via a bounded ``must_not document_id`` clause
        fed from this flag, so thousands of points never have to be patched on a doc-level toggle.

        Args:
            document_id (uuid.UUID): The document to toggle.
            enabled (bool): The new searchability state.

        Returns:
            bool: Whether the document existed (False → the router raises a 404).
        """
        # 1. One Postgres flip — the source of truth the search filter reads.
        async with self._postgres.session() as session:
            existed = await DocumentApi.set_enabled(session, document_id, enabled)
        if existed:
            self.logger.info(f"Document {document_id} enabled={enabled}")
        return existed

    async def set_documents_enabled(self, document_ids: Sequence[uuid.UUID], enabled: bool) -> int:
        """
        Bulk-toggle a set of documents' searchability — one Postgres statement, no Qdrant fan-out.

        The mass sibling of ``set_document_enabled``: because the document-level flag is read by the
        search filter (a bounded ``must_not document_id`` exclusion), flipping thousands of documents
        never has to patch a single Qdrant point. Returns how many rows actually changed so a bulk
        op can report ``updated`` distinctly from ``matched`` (already-in-state rows are not counted).

        Args:
            document_ids (Sequence[uuid.UUID]): The documents to toggle.
            enabled (bool): The new searchability state.

        Returns:
            int: The number of documents whose state actually changed.
        """
        # 1. One bulk Postgres flip — the source of truth the search filter reads.
        async with self._postgres.session() as session:
            updated = await DocumentApi.set_enabled_many(session, document_ids, enabled)
        self.logger.info(f"Bulk-toggled {updated} document(s) enabled={enabled}")
        return updated

    # -------------------- chunks --------------------
    async def set_chunks_enabled(
        self, chunk_ids: Sequence[uuid.UUID], enabled: bool
    ) -> list[ChunkToggle]:
        """
        Toggle chunks' searchability — set the override, flip the payload of embedded ones.

        For each known chunk: write ``enabled_override`` in Postgres, recompute the effective state
        (``override ?? role_default_enabled(role)``) and, if the chunk has a Qdrant point, flip that
        point's ``enabled`` scalar via set_payload (the vector is left untouched — reversible, no
        re-embed). A chunk that was never embedded has no point: enabling it cannot make it
        searchable here, so it is reported with ``reindex_required=True`` for a later on-demand embed.

        Args:
            chunk_ids (Sequence[uuid.UUID]): The chunks to toggle.
            enabled (bool): The desired state to store as the per-chunk override.

        Returns:
            list[ChunkToggle]: One outcome per KNOWN chunk (unknown ids are omitted — the router
            maps the gap to a 404 for the single-chunk route).
        """
        async with self._postgres.session() as session:
            # 1. Load the chunks; unknown ids simply drop out (reported as absent upstream).
            chunks = await ChunkApi.get_by_ids(session, chunk_ids)
            if not chunks:
                return []

            # 2. Resolve each chunk's Qdrant collection through its document (the point's home).
            collection_by_document = await self._collections_by_document(session, chunks)

            # 3. Apply the override + gather the point payload flips per Qdrant collection.
            outcomes, payloads_by_collection = self._apply_overrides(
                chunks, enabled, collection_by_document
            )

            # 4. Flip the embedded points' payload INSIDE the transaction — a Qdrant failure rolls
            #    the Postgres overrides back, keeping the two stores consistent on the common path.
            for name, payloads in payloads_by_collection.items():
                await QdrantIndexApi.set_payload(self._qdrant.raw, name, payloads)

        self.logger.info(f"Toggled {len(outcomes)} chunk(s) enabled={enabled}")
        return outcomes

    # -------------------- internals --------------------
    @staticmethod
    async def _collections_by_document(
        session: AsyncSession, chunks: Sequence[Chunk]
    ) -> dict[uuid.UUID, uuid.UUID]:
        """Map each chunk's document id to its collection id (the Qdrant collection key)."""
        document_ids = {chunk.document_id for chunk in chunks}
        documents = await DocumentApi.get_by_ids(session, list(document_ids))
        return {document.id: document.collection_id for document in documents}

    @staticmethod
    def _apply_overrides(
        chunks: Sequence[Chunk],
        enabled: bool,
        collection_by_document: dict[uuid.UUID, uuid.UUID],
    ) -> tuple[list[ChunkToggle], dict[str, dict[str, dict[str, bool]]]]:
        """
        Set each chunk's override and split them into 'flip the point' vs 'needs re-embed'.

        Returns:
            tuple: the per-chunk outcomes, and (Qdrant collection name → {point id → {enabled}})
            for the embedded chunks whose payload must be patched.
        """
        outcomes: list[ChunkToggle] = []
        payloads_by_collection: dict[str, dict[str, dict[str, bool]]] = defaultdict(dict)
        for chunk in chunks:
            # 1. The user's explicit choice becomes the override; effective = override ?? default.
            chunk.enabled_override = enabled
            effective = (
                chunk.enabled_override
                if chunk.enabled_override is not None
                else role_default_enabled(ChunkRole(chunk.role))
            )
            # 2. An embedded chunk has a point to flip; a never-embedded one being ENABLED genuinely
            #    needs a (deferred) re-embed — never fabricate a point to fake searchability.
            reindex_required = False
            if chunk.is_indexed:
                name = DatabaseHelpers.qdrant_collection_name(
                    collection_by_document[chunk.document_id]
                )
                payloads_by_collection[name][str(chunk.id)] = {ENABLED_KEY: effective}
            elif effective:
                reindex_required = True
            outcomes.append(
                ChunkToggle(chunk_id=chunk.id, enabled=effective, reindex_required=reindex_required)
            )
        return outcomes, payloads_by_collection


__all__ = ["EnablementFacade"]
