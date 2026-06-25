# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Mirrors the TEI /health response shape so DocForge and external callers can probe the
    service without any client-side changes. When models are still loading the response carries
    status="loading" and ready=False — callers should treat HTTP 503 as transient.

    Attributes:
        status (str): "ok" when models are loaded and ready; "loading" while startup is in progress.
        ready (bool): True only when both models are loaded and inference requests will be served.
        embed_model (str): HuggingFace model ID of the embedding model (from config).
        rerank_model (str): HuggingFace model ID of the reranking model (from config).
    """

    status: str = Field(..., description="'ok' when ready, 'loading' during startup.")
    ready: bool = Field(..., description="True when both models are loaded and inference is available.")
    embed_model: str = Field(..., description="HuggingFace model ID of the embed model.")
    rerank_model: str = Field(..., description="HuggingFace model ID of the rerank model.")
