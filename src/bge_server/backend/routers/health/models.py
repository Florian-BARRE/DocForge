# ====== Code Summary ======
# Pydantic response model for the GET /health endpoint.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """
    Response model for the GET /health liveness probe.

    Mirrors the TEI /health response shape so DocForge and external callers can probe the
    service without any client-side changes.

    Attributes:
        status (str): Always "ok" when the service is healthy.
        embed_model (str): HuggingFace model ID of the loaded embedding model.
        rerank_model (str): HuggingFace model ID of the loaded reranking model.
    """

    status: str = Field(..., description="Service health status — always 'ok' when healthy.")
    embed_model: str = Field(..., description="HuggingFace model ID of the loaded embed model.")
    rerank_model: str = Field(..., description="HuggingFace model ID of the loaded rerank model.")
