# ====== Code Summary ======
# The collections router — the single ``/collections`` router the app registers, assembled from the
# route-group modules: contract reads, insight probes (health/describe/storage/estimate), dry-run
# previews, lifecycle (create/delete), the PATCH, and corpus maintenance (reingest/trace purge).
# Every rejection carries an explicit HTTP code and a precise message. Non-route logic lives in
# helpers.py / blob_helpers.py / preview_helpers.py (pure) and store_sync.py (store follow-through).

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Local Project Imports ======
from .insight_routes import router as insight_router
from .lifecycle_routes import router as lifecycle_router
from .maintenance_routes import router as maintenance_router
from .preview_routes import router as preview_router
from .read_routes import router as read_router
from .update_routes import router as update_router

router = APIRouter()

# Read routes go FIRST: the literal ``GET /collections/contract-schema`` must be matched before the
# ``GET /collections/{collection_id}`` path parameter would capture it.
router.include_router(read_router)
router.include_router(insight_router)
router.include_router(preview_router)
router.include_router(lifecycle_router)
router.include_router(update_router)
router.include_router(maintenance_router)


__all__ = ["router"]
