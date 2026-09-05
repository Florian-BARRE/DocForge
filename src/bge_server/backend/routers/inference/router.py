# ====== Code Summary ======
# Route definitions for POST /embed, POST /embed_sparse, POST /embed_colbert, and POST /rerank.
# /embed, /embed_sparse, and /rerank implement the TEI HTTP contract so the DocForge `tei` embed
# provider and `bge_reranker` rerank provider can drive this service with zero provider-side
# changes. /embed_colbert is an internal DocForge convention (not part of TEI) exposing BGE-M3's
# native ColBERT multi-vector head. All inference is delegated to CONTEXT.batching_engine; no
# model logic here. Back-pressure: QueueFullError from the engine is translated to HTTP 503 with
# Retry-After: 1.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from libs.batching import QueueFullError

# ====== Local Project Imports ======
from .helpers import InferenceHelpers
from .models import (
    ColbertTokenVectors,
    EmbedAllResponse,
    EmbedRequest,
    RerankRequest,
    RerankResult,
    SparseToken,
)

router = APIRouter()

# Module-level logger for per-request tracing. All inference request lines go through
# this logger at DEBUG level — never INFO, to avoid flooding logs when polled at high rate.
logger = loggerplusplus.bind(identifier="InferenceRouter")


@router.post("/embed", response_model=list[list[float]])
@auto_handle_errors
async def embed(req: EmbedRequest) -> list[list[float]]:
    """
    Dense embeddings -- mirrors TEI's POST /embed.

    Encodes each input text into a 1024-dimensional L2-normalized float vector using
    BGE-M3's dense head. FlagEmbedding always normalizes dense output, so the ``normalize``
    field is accepted for TEI parity but has no additional effect.

    Concurrency: requests are submitted to the batching engine's dense queue. Multiple
    concurrent requests are coalesced into single batches to maximize GPU/CPU utilization.
    When the queue is full, HTTP 503 + Retry-After: 1 is returned immediately.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        list[list[float]]: One 1024-dim dense vector per input text.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG — never log text contents (may be large / sensitive)
    logger.debug(f"POST /embed: {len(texts)} inputs")

    # 3. Empty input — return immediately without touching the engine
    if not texts:
        return []

    # 4. Submit to the dense batching worker; translate back-pressure to HTTP 503
    try:
        return await CONTEXT.batching_engine.submit_embed_dense(texts)
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "1"},
        )


@router.post("/embed_sparse", response_model=list[list[SparseToken]])
@auto_handle_errors
async def embed_sparse(req: EmbedRequest) -> list[list[SparseToken]]:
    """
    Sparse (lexical) embeddings -- mirrors TEI's POST /embed_sparse response shape.

    BGE-M3's ``lexical_weights`` dict is re-shaped to TEI's
    ``[[{"index": int, "value": float}, ...], ...]`` format so the DocForge ``tei`` provider
    parses it unchanged.

    Concurrency: requests are submitted to the batching engine's sparse queue.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        list[list[SparseToken]]: Per text, a list of token index/weight pairs.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG
    logger.debug(f"POST /embed_sparse: {len(texts)} inputs")

    # 3. Empty input — return immediately
    if not texts:
        return []

    # 4. Submit to the sparse batching worker
    try:
        raw = await CONTEXT.batching_engine.submit_embed_sparse(texts)
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "1"},
        )

    # 5. Wrap each dict into the typed SparseToken model for response validation. The batching
    #    worker types weights as int | float, so pin each field to its declared type explicitly.
    return [
        [SparseToken(index=int(tok["index"]), value=float(tok["value"])) for tok in row]
        for row in raw
    ]


@router.post("/embed_all", response_model=EmbedAllResponse)
@auto_handle_errors
async def embed_all(req: EmbedRequest) -> EmbedAllResponse:
    """
    Combined dense + sparse embeddings in ONE forward pass.

    A caller needing both representations would otherwise hit /embed and /embed_sparse and pay
    two BGE-M3 forward passes; this route requests both heads from a single pass and returns the
    two sub-shapes unchanged (``dense`` identical to POST /embed, ``sparse`` identical to POST
    /embed_sparse). Not part of the TEI contract — the DocForge app falls back to the two
    separate routes when this one is unavailable.

    Unlike the batched dense/sparse queues, this path calls the model directly (no cross-request
    coalescing) but is still serialised on the shared embed lock, so it never overlaps a dense or
    sparse batch on the shared model instance. Request-size ceilings are enforced by EmbedRequest
    (HTTP 422), exactly as for /embed and /embed_sparse. Back-pressure: this route has no
    BatchQueueWorker queue of its own, so the engine bounds its admission with an in-flight
    counter instead (see BatchingEngine.embed_all) and raises QueueFullError past that cap --
    translated to HTTP 503 + Retry-After: 1 here, exactly like the four queued routes.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        EmbedAllResponse: ``{dense, sparse}`` for the input texts.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG — never log text contents (may be large / sensitive)
    logger.debug(f"POST /embed_all: {len(texts)} inputs")

    # 3. Empty input — return immediately without touching the engine
    if not texts:
        return EmbedAllResponse(dense=[], sparse=[])

    # 4. One combined forward pass through the engine (serialised on the shared embed lock).
    #    max_length matches the value the engine's dense/sparse workers use (from the same config),
    #    so the returned vectors are identical to the two separate routes. Translate the engine's
    #    in-flight-cap back-pressure the same way the four queued routes translate QueueFullError.
    try:
        dense, sparse_raw = await CONTEXT.batching_engine.embed_all(
            texts, max_length=CONTEXT.CONFIG.BGE_M3_MAX_LENGTH
        )
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "1"},
        )

    # 5. Wrap each sparse dict into the typed SparseToken model (matching /embed_sparse), pinning
    #    each field to its declared type (the engine types weights as int | float).
    return EmbedAllResponse(
        dense=dense,
        sparse=[
            [SparseToken(index=int(tok["index"]), value=float(tok["value"])) for tok in row]
            for row in sparse_raw
        ],
    )


@router.post("/embed_colbert", response_model=list[list[list[float]]])
@auto_handle_errors
async def embed_colbert(req: EmbedRequest) -> ColbertTokenVectors:
    """
    ColBERT multi-vector embeddings -- BGE-M3 native, NOT part of the TEI contract.

    Encodes each input text into a variable-length list of per-token 1024-dim
    L2-normalized float vectors using BGE-M3's colbert head. Internal DocForge
    convention only; no upstream TEI endpoint to mirror.

    Concurrency: requests are submitted to the batching engine's colbert queue.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        list[list[list[float]]]: Per input text, a list of per-token 1024-dim vectors.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG — never log text contents (may be large / sensitive)
    logger.debug(f"POST /embed_colbert: {len(texts)} inputs")

    # 3. Empty input — return immediately without touching the engine
    if not texts:
        return []

    # 4. Submit to the colbert batching worker; translate back-pressure to HTTP 503
    try:
        return await CONTEXT.batching_engine.submit_embed_colbert(texts)
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "1"},
        )


@router.post("/rerank", response_model=list[RerankResult])
@auto_handle_errors
async def rerank(req: RerankRequest) -> list[RerankResult]:
    """
    Cross-encoder rerank -- mirrors TEI's POST /rerank.

    Scores each candidate text against the query using BGE-reranker-v2-m3. Scores are
    sigmoid-normalized to [0, 1]. Results are returned score-descending, matching TEI's own
    /rerank response order. The DocForge ``bge_reranker`` provider maps each result back onto
    its candidate by ``index`` and does not depend on response order, so this ordering is a
    TEI-parity concern, not a correctness one.

    Concurrency: requests are submitted to the batching engine's rerank queue.

    Args:
        req (RerankRequest): Request body with query and candidate texts.

    Returns:
        list[RerankResult]: One ``{"index": i, "score": s}`` per candidate text, sorted
            score-descending (best match first).
    """
    # 1. Log batch size at DEBUG — never log query text or candidate contents
    logger.debug(f"POST /rerank: {len(req.texts)} candidates")

    # 2. Empty candidate list — return immediately (no engine call needed)
    if not req.texts:
        return []

    # 3. Submit to the rerank batching worker
    try:
        raw = await CONTEXT.batching_engine.submit_rerank(req.query, req.texts)
    except QueueFullError:
        raise HTTPException(
            status_code=503,
            detail={"error": "server overloaded — try again shortly"},
            headers={"Retry-After": "1"},
        )

    # 4. Wrap each dict into the typed RerankResult model for response validation, pinning each
    #    field to its declared type (the worker types the payload as int | float).
    return [RerankResult(index=int(item["index"]), score=float(item["score"])) for item in raw]
