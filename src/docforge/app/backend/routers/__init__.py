# Routers are organized as a hierarchy that mirrors the resource tree:
#   collections/ → { config/, documents/ → { search/, files/, chunks/, pages/ } }

# --------------------- Health -------------------- #
from .health.router import router as health_router

# --------------------- Auth ---------------------- #
from .auth.router import router as auth_router

# ------------------- Discovery -------------------- #
from .discovery.router import router as discovery_router

# ------------------- Collections ----------------- #
from .collections.router import router as collection_router

# ----------------- Collection config -------------- #
from .collections.config.router import router as config_router

# ----------------- Collection limits -------------- #
from .collections.limits.router import router as limits_router

# ----------------- Collection metagen ------------- #
from .collections.metagen.router import router as metagen_router

# -------------------- Documents ------------------ #
from .collections.documents.router import router as document_router

# ---------------- Documents · search -------------- #
from .collections.documents.search.router import router as search_router

# ---------------- Documents · files --------------- #
from .collections.documents.files.router import router as files_router

# --------------- Documents · chunks --------------- #
from .collections.documents.chunks.router import router as chunks_router

# ---------------- Documents · pages --------------- #
from .collections.documents.pages.router import router as pages_router

# -------------------- Jobs ------------------------ #
from .jobs.router import router as jobs_router

# ------------------- Monitoring ------------------- #
from .monitoring.router import router as monitoring_router

# ------------------- Public API ------------------ #
__all__ = [
    "health_router",
    "auth_router",
    "discovery_router",
    "collection_router",
    "config_router",
    "limits_router",
    "metagen_router",
    "document_router",
    "search_router",
    "files_router",
    "chunks_router",
    "pages_router",
    "jobs_router",
    "monitoring_router",
]
