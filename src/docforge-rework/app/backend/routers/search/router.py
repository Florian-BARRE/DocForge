# ====== Code Summary ======
# The search router — the retrieval READ path behind a collection. It embeds the query with the
# collection's OWN embedder (so query and chunk vectors share a space), names the query vectors with
# the SAME constants the persistence side writes (content_dense / content_bm25 — never string
# literals), translates the requested filters into typed Conditions over the filterable fields, then
# delegates the Qdrant RRF fusion + Postgres hydration to the search facade. Every rejection carries
# an explicit HTTP code: 404 unknown collection, 409 no embedder wired, 422 non-filterable filter.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.qdrant import SparseVec, VectorNames

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors
from .embedder import QueryEmbedder
from .helpers import SearchHelpers
from .models import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/collections/{collection_id}/search", response_model=SearchResponse)
@auto_handle_errors
async def search_collection(collection_id: uuid.UUID, request: SearchRequest) -> SearchResponse:
    """
    Run a hybrid search over a collection and return ranked, hydrated chunk hits.

    Returns:
        SearchResponse: The echoed query and its hits, best first. 404 when the collection is
        unknown, 409 when it has no embedder wired, 422 when a filter names a non-filterable field.
    """
    # 1. The collection must exist — everything (its embedder, its schema) derives from it.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Locate the collection's embed node — without it there are no vectors to search.
    embed_blob = SearchHelpers.embed_node_blob(collection.pipeline)
    if embed_blob is None:
        raise HTTPException(
            status_code=409, detail="Collection has no embed node — search is unavailable."
        )

    # 3. Embed the QUERY with the collection's own embedder (dense always, sparse when supported).
    dense_vector, sparse_vector = await QueryEmbedder(embed_blob).embed(request.query)

    # 4. Name the query vectors with the SAME constants the persistence side writes.
    dense: dict[str, list[float]] = {VectorNames.CONTENT_DENSE: dense_vector}
    sparse: dict[str, SparseVec] | None = (
        {VectorNames.CONTENT_SPARSE: sparse_vector} if sparse_vector is not None else None
    )

    # 5. Translate the requested filters into typed Conditions over the filterable fields.
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    conditions, invalid = SearchHelpers.build_conditions(request.filters, schema)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Not a filterable field for this collection: {sorted(invalid)}",
        )

    # 6. Delegate the vector fusion + Postgres hydration to the facade.
    hits = await CONTEXT.database.search.hybrid(
        collection_id,
        dense=dense,
        sparse=sparse,
        conditions=conditions,
        limit=request.limit,
    )

    # 7. Shape the flat, client-facing response.
    return SearchResponse(query=request.query, hits=[SearchHelpers.to_hit(hit) for hit in hits])


__all__ = ["router"]
