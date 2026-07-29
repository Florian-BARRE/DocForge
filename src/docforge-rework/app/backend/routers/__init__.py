# -------------------- Auth (API-key management) ------------------- #
from .auth.router import router as auth_router

# -------------------- Collections (contract CRUD) ------------------- #
from .collections.router import router as collections_router

# -------------------- Documents (admission) ------------------- #
from .documents.router import router as documents_router

# -------------------- Explorer (document read surface) ------------------- #
from .explorer.router import router as explorer_router

# -------------------- Search (retrieval read surface) ------------------- #
from .search.router import router as search_router

# -------------------- Blobs (byte streaming) ------------------- #
from .blobs.router import router as blobs_router

# -------------------- Jobs (ingestion status) ------------------- #
from .jobs.router import router as jobs_router

# -------------------- Pipelines (design surface) ------------------- #
from .pipelines.router import router as pipelines_router

# -------------------- Scalar (API reference) ------------------- #
from .scalar.router import router as scalar_router

# -------------------- Health (public liveness probe) ------------------- #
from .health.router import router as health_router

# ------------------- Public API ------------------- #
__all__ = [
    "auth_router",
    "collections_router",
    "documents_router",
    "explorer_router",
    "search_router",
    "blobs_router",
    "jobs_router",
    "pipelines_router",
    "scalar_router",
    "health_router",
]
