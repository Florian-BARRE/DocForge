# ====== Code Summary ======
# StageUsageSummer — the worker's per-stage ingest cost meter. The summing/pricing logic now lives in
# the shared UsageSummer (reused by the app-side inline search meter); this keeps the historical
# worker-facing name as a thin alias so the ingest meter's call sites read unchanged.

# ====== Internal Project Imports ======
from shared_libs.pipelines.usage import UsageSummer

# The per-stage ingest meter is the shared summer under its worker-facing name.
StageUsageSummer = UsageSummer

__all__ = ["StageUsageSummer"]
