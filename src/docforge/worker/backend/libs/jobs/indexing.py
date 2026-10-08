# ====== Code Summary ======
# DocumentIndexer — the shared tail of an ingest AND a replay run: push the translated points into
# Qdrant (upsert then drop the stale leftovers, through IngestionFacade.index), then the two best-effort
# denormalisations onto the fresh points (filterable doc-scope payload + doc-scope metadata vectors).
# A denormalisation hiccup never fails a run whose content is already persisted — the backfill jobs are
# the explicit repair paths.

# ====== Standard Library Imports ======
import uuid
from typing import Any


class DocumentIndexer:
    """Static-only: index a translated run's points and re-sync the document-scope payload/vectors."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("DocumentIndexer is a static-only class and cannot be instantiated.")

    @staticmethod
    async def index(
        database: Any,
        collection_id: uuid.UUID,
        document_id: uuid.UUID,
        translated: Any,
        logger: Any,
    ) -> None:
        """
        Index the points (when any) and run the best-effort filter + meta-vector syncs.

        Args:
            database (Any): The worker's Database facade.
            collection_id (uuid.UUID): The owning collection.
            document_id (uuid.UUID): The document whose points these are.
            translated (Any): The RunTranslator output (``points`` + ``dense_dim`` + ``layout``).
            logger (Any): The caller's logger (a sync hiccup is logged, never raised).
        """
        # 1. No embed stage → no points: Qdrant is skipped entirely.
        if not translated.points:
            return
        await database.ingestion.index(
            collection_id,
            document_id,
            translated.dense_dim,
            translated.points,
            layout=getattr(translated, "layout", None),
        )
        # 2. Denormalise the filterable doc-scope metadata onto the fresh points (best-effort).
        try:
            await database.filters.sync_document_filter_payloads(document_id)
        except Exception as filter_exc:
            logger.warning(
                f"Filter denormalisation failed for document {document_id} "
                f"(ingestion kept; repair via backfill): {filter_exc}"
            )
        # 3. Populate the doc-scope metadata named vectors on the same points (best-effort).
        try:
            await database.meta_vectors.sync_document_meta_vectors(document_id)
        except Exception as meta_exc:
            logger.warning(
                f"Meta-vector population failed for document {document_id} "
                f"(ingestion kept; repair via backfill): {meta_exc}"
            )


__all__ = ["DocumentIndexer"]
