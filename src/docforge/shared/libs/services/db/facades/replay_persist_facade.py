# ====== Code Summary ======
# ReplayPersistFacade — the WRITE side of a replay-from-stage run: persists ONLY the layers downstream
# of the replayed stage, from the same translated payload a full run produces. Blocks, tables, figures,
# pages, blobs and document facts are never touched (the IR the replay stood on stays). In ONE
# transaction: the figure enrichments are replaced when enrich re-ran; the generated document-scope
# metadata when the run delivered document metadata; and the chunks (rows + composition + generated
# chunk metadata) always — the deterministic (document, ordinal) chunk ids keep point ids stable. The
# document is finalized DONE with its chunk count + optional 0-chunk warning; vectors are pushed by the
# caller through the normal ``IngestionFacade.index`` path (upsert, then purge the stale leftovers).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql import PostgresClient
from shared_libs.services.db.postgresql.apis import ChunkApi, DocumentApi, IRApi

# ====== Local Project Imports ======
from .payloads import IngestionPayload


class ReplayPersistFacade(LoggerClass):
    """Persist a replay's downstream layers only (enrichments / generated metadata / chunks)."""

    def __init__(self, postgres: PostgresClient) -> None:
        LoggerClass.__init__(self)
        self._postgres = postgres

    async def save_downstream(
        self,
        document_id: uuid.UUID,
        payload: IngestionPayload,
        *,
        replace_enrichments: bool,
        replace_document_meta: bool,
        warning_reason: str | None = None,
    ) -> None:
        """
        Replace the downstream layers of one document, in ONE transaction.

        Args:
            document_id (uuid.UUID): The replayed document.
            payload (IngestionPayload): The translated run (only its downstream rows are read).
            replace_enrichments (bool): Rewrite the figure enrichment rows (enrich re-ran).
            replace_document_meta (bool): Rewrite the GENERATED document-scope values (USER rows
                always survive).
            warning_reason (str | None): The 0-chunk warning (None clears a stale one).
        """
        async with self._postgres.session() as session:
            # 1. The IR-side layer, only when enrich re-ran (blocks + details stay).
            if replace_enrichments:
                await IRApi.replace_enrichments(session, document_id, payload.enrichments)
            # 2. The generated document-scope values, only when the run delivered them.
            if replace_document_meta:
                await DocumentApi.replace_metadata(session, document_id, payload.document_metadata)
            # 3. The chunks: purge then insert (composition + generated chunk metadata with them).
            await ChunkApi.delete_for_document(session, document_id)
            await ChunkApi.persist_chunks(
                session, payload.chunks, payload.composition, metadata=payload.chunk_metadata
            )
            # 4. Done (guarded against a racing force-cancel), chunk count denormalized.
            await DocumentApi.finalize_done(
                session, document_id, warning_reason=warning_reason, chunk_count=len(payload.chunks)
            )
        self.logger.info(
            f"Replay saved for document {document_id}: {len(payload.chunks)} chunks "
            f"(enrichments={'replaced' if replace_enrichments else 'kept'}, "
            f"document metadata={'replaced' if replace_document_meta else 'kept'})"
        )


__all__ = ["ReplayPersistFacade"]
