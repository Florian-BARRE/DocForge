# ====== Code Summary ======
# Local BGE model-suite micro-service: serves dense + sparse EMBEDDING (BGE-M3) AND
# cross-encoder RERANK (BGE-reranker-v2-m3) over one HTTP API. Replaces the off-the-shelf
# HuggingFace TEI containers (which crash on BGE-M3's ONNX backend and can't do BGE-M3 sparse).
#
# Implements the SAME contract as TEI (/embed, /embed_sparse, /rerank, /health), so the
# existing DocForge `tei` embed provider AND `bge_reranker` rerank provider drive it with NO
# new provider code — just point TEI_BASE_URL and BGE_RERANKER_URL at this one service.
#
# Both models run via FlagEmbedding (torch), loaded once at startup. CPU by default.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from pydantic import BaseModel, Field

# ── Model identity / runtime config (env-overridable) ─────────────────────────────
EMBED_MODEL_ID = os.environ.get("BGE_M3_MODEL", "BAAI/bge-m3")
RERANK_MODEL_ID = os.environ.get("BGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
USE_FP16 = os.environ.get("BGE_FP16", os.environ.get("BGE_M3_FP16", "false")).lower() in ("1", "true", "yes")
MAX_LENGTH = int(os.environ.get("BGE_M3_MAX_LENGTH", "8192"))

# Loaded models held on app state, initialized once at startup (lifespan).
_STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the BGE embedding + reranker models once at startup; release on shutdown."""
    # Imported here so the module imports cheaply and the heavy model loads happen only
    # when the service actually boots.
    from FlagEmbedding import BGEM3FlagModel, FlagReranker

    _STATE["model"] = BGEM3FlagModel(EMBED_MODEL_ID, use_fp16=USE_FP16)
    _STATE["reranker"] = FlagReranker(RERANK_MODEL_ID, use_fp16=USE_FP16)
    yield
    _STATE.clear()


app = FastAPI(title="BGE model-suite (embed dense+sparse + rerank)", version="2.0.0", lifespan=lifespan)


# ── Request models ────────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    """TEI-compatible embed request body."""

    inputs: list[str] | str = Field(..., description="One text or a list of texts to embed.")
    normalize: bool = Field(default=True, description="L2-normalize dense vectors (TEI parity).")
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")


class RerankRequest(BaseModel):
    """TEI-compatible rerank request body."""

    query: str = Field(..., description="The search query.")
    texts: list[str] = Field(..., description="Candidate texts to score against the query.")
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")


def _as_list(inputs: list[str] | str) -> list[str]:
    """Normalize the TEI `inputs` field (str or list) into a list of texts."""
    return [inputs] if isinstance(inputs, str) else list(inputs)


# ── Endpoints (TEI contract) ────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — mirrors TEI's GET /health."""
    return {"status": "ok", "embed_model": EMBED_MODEL_ID, "rerank_model": RERANK_MODEL_ID}


@app.post("/embed")
async def embed(req: EmbedRequest) -> list[list[float]]:
    """
    Dense embeddings — mirrors TEI's POST /embed.

    Returns:
        list[list[float]]: One dense vector per input text (1024-dim for BGE-M3).
    """
    texts = _as_list(req.inputs)
    if not texts:
        return []
    out = _STATE["model"].encode(
        texts, return_dense=True, return_sparse=False, return_colbert_vecs=False,
        max_length=MAX_LENGTH,
    )
    # FlagEmbedding already L2-normalizes dense vectors; `normalize` kept for TEI parity.
    return [vec.tolist() for vec in out["dense_vecs"]]


@app.post("/embed_sparse")
async def embed_sparse(req: EmbedRequest) -> list[list[dict[str, float]]]:
    """
    Sparse (lexical) embeddings — mirrors TEI's POST /embed_sparse response shape.

    BGE-M3's ``lexical_weights`` is a dict ``{token_id(str): weight(float)}`` per text; it is
    re-shaped to TEI's ``[[{"index": int, "value": float}, ...], ...]`` so the DocForge `tei`
    provider parses it unchanged.

    Returns:
        list[list[dict]]: Per text, a list of ``{"index": token_id, "value": weight}`` entries.
    """
    texts = _as_list(req.inputs)
    if not texts:
        return []
    out = _STATE["model"].encode(
        texts, return_dense=False, return_sparse=True, return_colbert_vecs=False,
        max_length=MAX_LENGTH,
    )
    result: list[list[dict[str, float]]] = []
    for weights in out["lexical_weights"]:
        # weights: {token_id(str|int): weight(float)} — emit TEI's index/value token list.
        result.append([{"index": int(tok), "value": float(w)} for tok, w in weights.items()])
    return result


@app.post("/rerank")
async def rerank(req: RerankRequest) -> list[dict[str, Any]]:
    """
    Cross-encoder rerank — mirrors TEI's POST /rerank.

    Scores each candidate text against the query with BGE-reranker-v2-m3 and returns
    ``[{"index": int, "score": float}, ...]`` in INPUT order (the DocForge bge_reranker
    provider re-sorts by index, so order is not significant). Scores are sigmoid-normalized
    to [0, 1] (``normalize=True``) for stable thresholds.

    Returns:
        list[dict]: One ``{"index": i, "score": s}`` per input text, aligned with ``texts``.
    """
    if not req.texts:
        return []
    pairs = [[req.query, text] for text in req.texts]
    scores = _STATE["reranker"].compute_score(pairs, normalize=True)
    # compute_score returns a bare float for a single pair — normalize to a list.
    if not isinstance(scores, list):
        scores = [scores]
    return [{"index": i, "score": float(s)} for i, s in enumerate(scores)]
