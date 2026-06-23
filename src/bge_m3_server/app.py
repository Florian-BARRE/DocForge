# ====== Code Summary ======
# Local BGE-M3 embedding micro-service exposing dense + sparse over HTTP.
# Implements the SAME contract as HuggingFace TEI (/embed, /embed_sparse, /health) so the
# existing DocForge `tei` embed provider drives it with no new provider code — but unlike TEI,
# it serves BGE-M3's NATIVE multilingual sparse (lexical weights), which TEI cannot.
#
# BGE-M3 is a single multilingual model producing dense (1024-dim) + sparse (lexical weights)
# in one forward pass via FlagEmbedding.BGEM3FlagModel — so one model, one service, both vectors.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from pydantic import BaseModel, Field

# ── Model identity / runtime config (env-overridable) ─────────────────────────────
MODEL_ID = os.environ.get("BGE_M3_MODEL", "BAAI/bge-m3")
USE_FP16 = os.environ.get("BGE_M3_FP16", "false").lower() in ("1", "true", "yes")
MAX_LENGTH = int(os.environ.get("BGE_M3_MAX_LENGTH", "8192"))

# The loaded model is held on the app state, initialized once at startup (lifespan).
_STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load BGE-M3 once at startup; release it on shutdown."""
    # Imported here so the module imports cheaply (e.g. for tooling) and the heavy
    # model load happens only when the service actually boots.
    from FlagEmbedding import BGEM3FlagModel

    _STATE["model"] = BGEM3FlagModel(MODEL_ID, use_fp16=USE_FP16)
    yield
    _STATE.clear()


app = FastAPI(title="BGE-M3 dense+sparse embedding server", version="1.0.0", lifespan=lifespan)


# ── Request models ────────────────────────────────────────────────────────────────

class EmbedRequest(BaseModel):
    """TEI-compatible embed request body."""

    inputs: list[str] | str = Field(..., description="One text or a list of texts to embed.")
    normalize: bool = Field(default=True, description="L2-normalize dense vectors (TEI parity).")
    truncate: bool = Field(default=True, description="Truncate inputs to the model max length.")


def _as_list(inputs: list[str] | str) -> list[str]:
    """Normalize the TEI `inputs` field (str or list) into a list of texts."""
    return [inputs] if isinstance(inputs, str) else list(inputs)


# ── Endpoints (TEI contract) ────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — mirrors TEI's GET /health."""
    return {"status": "ok", "model": MODEL_ID}


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
