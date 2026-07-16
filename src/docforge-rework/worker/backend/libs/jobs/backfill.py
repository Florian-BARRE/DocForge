# ====== Code Summary ======
# The backfill_collection_filters arq task — the one-off maintenance path that denormalises every
# document's filterable document-scope metadata onto its chunk Qdrant points for an ENTIRE
# collection (data ingested before the write-side hook existed). Pure set_payload through the
# FilterSyncFacade: no re-embed, idempotent, safe to re-run. Enqueue it once per collection.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT


async def backfill_collection_filters(ctx: dict[str, Any], collection_id: str) -> dict[str, int]:
    """
    Backfill filterable document-scope metadata onto every chunk point of a collection.

    Args:
        ctx (dict): arq's context dict (unused — services live on CONTEXT).
        collection_id (str): The collection to backfill (UUID as string, the queue carries strings).

    Returns:
        dict[str, int]: ``{"documents": n, "points": m}`` — documents patched and points touched.
    """
    documents, points = await CONTEXT.database.filters.backfill_collection_filter_payloads(
        uuid.UUID(collection_id)
    )
    CONTEXT.logger.info(
        f"Backfill filters done for collection {collection_id}: "
        f"{documents} document(s), {points} point(s)"
    )
    return {"documents": documents, "points": points}


__all__ = ["backfill_collection_filters"]
