# ====== Code Summary ======
# BgeHealthResponse: the GET /health body of the BGE host. It extends the shared core HealthResponse
# (status, ready, detail, device) with the two model identities the BGE service has always reported.

# ====== Third-Party Library Imports ======
from model_server_core import HealthResponse
from pydantic import Field


class BgeHealthResponse(HealthResponse):
    """
    Response model for the GET /health liveness probe.

    Mirrors the TEI /health response shape so DocForge and external callers can probe the
    service without any client-side changes. When models are still loading the response carries
    status="loading" and ready=False — callers should treat HTTP 503 as transient.

    Attributes:
        embed_model (str): HuggingFace model ID of the embedding model (from config).
        rerank_model (str): HuggingFace model ID of the reranking model (from config).
    """

    embed_model: str = Field(..., description="HuggingFace model ID of the embed model.")
    rerank_model: str = Field(..., description="HuggingFace model ID of the rerank model.")
