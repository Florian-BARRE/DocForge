# ====== Code Summary ======
# Response models for the jobs resource, mirrored field-for-field from the DocForge backend router
# models. The classes live in sub-modules by concern (status, trace events, workers, statistics) and are
# re-exported here, so ``docforge_sdk.models.jobs`` stays the import path it always was.

# ====== Local Project Imports ======
from .._reexport import pin_module_path
from .events import JobEvent, JobEventPayload, JobTrace
from .stats import (
    CollectionCost,
    CollectionFailureBucket,
    FailureBreakdown,
    FailureBucket,
    JobTimeseries,
    NewFailures,
    QueueDepth,
    StageDurations,
    TimeseriesBucket,
)
from .status import JobPage, JobStatus
from .workers import CancelResult, WorkerActivity, WorkersLive

# ------------------- Public API ------------------- #
__all__ = [
    "JobStatus",
    "JobPage",
    "JobEvent",
    "JobEventPayload",
    "JobTrace",
    "WorkerActivity",
    "WorkersLive",
    "CancelResult",
    "QueueDepth",
    "StageDurations",
    "CollectionCost",
    "FailureBucket",
    "CollectionFailureBucket",
    "FailureBreakdown",
    "TimeseriesBucket",
    "JobTimeseries",
    "NewFailures",
]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.models.jobs``.
pin_module_path(__name__, globals(), __all__)
