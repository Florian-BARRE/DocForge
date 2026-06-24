# ====== Code Summary ======
# Route definitions for POST /embed, POST /embed_sparse, and POST /rerank.
# These three endpoints implement the TEI HTTP contract so the DocForge `tei` embed provider
# and `bge_reranker` rerank provider can drive this service with zero provider-side changes.
# All inference is delegated to CONTEXT.bge_models (BgeModelsService); no model logic here.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors

# ====== Local Project Imports ======
from .helpers import InferenceHelpers
from .models import EmbedRequest, RerankRequest, RerankResult, SparseToken

router = APIRouter()

# Module-level logger for per-request tracing. All inference request lines go through
# this logger at DEBUG level — never INFO, to avoid flooding logs when polled at high rate.
logger = loggerplusplus.bind(identifier="InferenceRouter")


@router.post("/embed", response_model=list[list[float]])
@auto_handle_errors
async def embed(req: EmbedRequest) -> list[list[float]]:
    """
    Dense embeddings — mirrors TEI's POST /embed.

    Encodes each input text into a 1024-dimensional L2-normalized float vector using
    BGE-M3's dense head. FlagEmbedding always normalizes dense output, so the ``normalize``
    field is accepted for TEI parity but has no additional effect.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        list[list[float]]: One 1024-dim dense vector per input text.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG — never log text contents (may be large / sensitive)
    logger.debug(f"POST /embed: {len(texts)} inputs")

    if not texts:
        return []

    # 3. Delegate encode to the model service via CONTEXT
    return CONTEXT.bge_models.encode_dense(texts, CONTEXT.CONFIG.BGE_M3_MAX_LENGTH)


@router.post("/embed_sparse", response_model=list[list[SparseToken]])
@auto_handle_errors
async def embed_sparse(req: EmbedRequest) -> list[list[SparseToken]]:
    """
    Sparse (lexical) embeddings — mirrors TEI's POST /embed_sparse response shape.

    BGE-M3's ``lexical_weights`` dict is re-shaped to TEI's
    ``[[{"index": int, "value": float}, ...], ...]`` format so the DocForge ``tei`` provider
    parses it unchanged.

    Args:
        req (EmbedRequest): Request body with texts to embed.

    Returns:
        list[list[SparseToken]]: Per text, a list of token index/weight pairs.
    """
    # 1. Normalize the TEI inputs field (str | list[str]) into a list
    texts = InferenceHelpers.as_list(req.inputs)

    # 2. Log batch size at DEBUG — never log text contents (may be large / sensitive)
    logger.debug(f"POST /embed_sparse: {len(texts)} inputs")

    if not texts:
        return []

    # 3. Delegate sparse encode to the model service via CONTEXT
    raw = CONTEXT.bge_models.encode_sparse(texts, CONTEXT.CONFIG.BGE_M3_MAX_LENGTH)

    # 4. Wrap each dict into the typed SparseToken model for response validation
    return [[SparseToken(**tok) for tok in row] for row in raw]


@router.post("/rerank", response_model=list[RerankResult])
@auto_handle_errors
async def rerank(req: RerankRequest) -> list[RerankResult]:
    """
    Cross-encoder rerank — mirrors TEI's POST /rerank.

    Scores each candidate text against the query using BGE-reranker-v2-m3. Scores are
    sigmoid-normalized to [0, 1]. Results are returned in INPUT order — the DocForge
    ``bge_reranker`` provider re-sorts by index.

    Args:
        req (RerankRequest): Request body with query and candidate texts.

    Returns:
        list[RerankResult]: One ``{"index": i, "score": s}`` per candidate text.
    """
    # 1. Log batch size at DEBUG — never log query text or candidate contents
    logger.debug(f"POST /rerank: {len(req.texts)} candidates")

    # 2. Empty candidate list — return immediately
    if not req.texts:
        return []

    # 3. Delegate rerank scoring to the model service via CONTEXT
    raw = CONTEXT.bge_models.compute_rerank_scores(req.query, req.texts)

    # 4. Wrap each dict into the typed RerankResult model for response validation
    return [RerankResult(**item) for item in raw]
