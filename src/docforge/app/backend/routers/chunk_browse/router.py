# ====== Code Summary ======
# The chunk-browse router — POST /collections/{collection_id}/chunks/browse lists a collection's chunks
# matching a filter map WITHOUT a query (no embedding, no ranking), one ordered keyset page at a time
# (document id, then chunk_index). It reuses the search route's filter gate (same 422s, same stored-
# value resolution + hints), the search hit shape + return_fields projection (geometry off by default)
# and, below it, the search's disabled-chunk/document exclusion — a browse can never list what a
# search would hide. The listing itself lives in CONTEXT.chunk_browser.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import Capability, require
from ...libs.search import (
    BrowseCursor,
    BrowseCursorError,
    HitProjection,
    SearchCollectionSpecs,
    ZeroHitHintBuilder,
)
from ...libs.search.hit_projection import GEOMETRY_FIELDS
from ...utils.error_handling import auto_handle_errors
from ..search.filter_gate import SearchFilterGate
from ..search.hit_mapper import SearchHitMapper
from ..search.model_mapper import SearchModelMapper
from .models import ChunkBrowseRequest, ChunkBrowseResponse

router = APIRouter(tags=["search"])

# A browse has no query, so no score: the field is neither returned nor selectable.
_NO_SCORE = frozenset({"score"})

# The default browse fields: every hit field but the score and the drawing geometry (page_number stays
# — the reader-facing page to cite).
_DEFAULT_FIELDS = sorted(
    set(SearchHitMapper.projectable_fields(_NO_SCORE)) - (GEOMETRY_FIELDS - {"page_number"})
)


@router.post(
    "/collections/{collection_id}/chunks/browse",
    response_model=ChunkBrowseResponse,
    # Unrequested hit fields stay UNSET → absent from the wire (the score is never set at all).
    response_model_exclude_unset=True,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def browse_chunks(
    collection_id: uuid.UUID, request: ChunkBrowseRequest
) -> ChunkBrowseResponse:
    """
    List a collection's chunks matching a filter, without a query, in (document, chunk_index) order.

    Returns:
        ChunkBrowseResponse: One page of chunks, the next page's cursor and any filter hints. 404
        when the collection is unknown; 422 on an invalid filter, an unknown return_fields name, or
        a cursor this API did not issue.
    """
    # 0. Caller errors first, before any read: the field projection and the cursor.
    allowed_fields = SearchHitMapper.projectable_fields(_NO_SCORE)
    projection, unknown_fields = HitProjection.from_request(
        request.return_fields if request.return_fields is not None else _DEFAULT_FIELDS,
        allowed_fields,
    )
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown return_fields {unknown_fields} — allowed: {allowed_fields} or "
            f"'metadata.<field>'.",
        )
    try:
        cursor = BrowseCursor.decode(request.cursor) if request.cursor is not None else None
    except BrowseCursorError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 1. The collection must exist.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. The SAME filter gate + stored-value resolution as the search route.
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    resolution = await SearchFilterGate.resolve(request.filters, schema)

    # 3. One ordered page (exclusion of disabled chunks/documents baked in below).
    page = await CONTEXT.chunk_browser.browse(
        collection_id,
        filters=resolution.filters if request.filters is not None else None,
        limit=request.limit,
        cursor=cursor,
        text_fields=resolution.text_fields,
        title_field=SearchCollectionSpecs.title_field_spec(collection, schema),
        projection=projection,
    )

    # 4. Shape the page; a zero-hit "likely culprit" hint only explains an empty FIRST page (an
    #    empty later page just means the listing ended).
    hints = resolution.hints + (
        ZeroHitHintBuilder.build(resolution, len(page.hits)) if cursor is None else []
    )
    return ChunkBrowseResponse(
        chunks=SearchHitMapper.map(page.hits, projection),
        next_cursor=page.next_cursor.encode() if page.next_cursor is not None else None,
        hints=[SearchModelMapper.to_hint_model(hint) for hint in hints],
    )


__all__ = ["router"]
