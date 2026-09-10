# ---------------------- Ingestion job ---------------------- #
from .core import ingest_document

# ---------------------- Maintenance jobs ---------------------- #
from .backfill import backfill_collection_filters, backfill_collection_meta_vectors
from .reaper import reap_stuck_jobs

# ---------------------- Collection transfer jobs ---------------------- #
from .transfer import export_collection, import_collection
from .transfer_gc import gc_expired_transfers
from .transfer_reaper import reap_stuck_transfers

# ---------------------- Audit retention ---------------------- #
from .audit_gc import gc_audit_log

# ---------------------- Job-history retention ---------------------- #
from .history_gc import gc_job_history

# ---------------------- Idempotency retention ---------------------- #
from .idempotency_gc import gc_idempotency_keys

# ---------------------- Stage-artifact cache retention ---------------------- #
from .artifact_cache_gc import gc_artifact_cache

# ---------------------- Execution-trace retention ---------------------- #
from .trace_gc import gc_trace_payloads

# ---------------------- Live progress ---------------------- #
from .progress import JobProgressRecorder

# ---------------------- Cooperative cancel ---------------------- #
from .cancellation import CancellationGuard, JobCancelledError

# ---------------------- Correlation binding ---------------------- #
from .correlation import with_correlation

# ------------------- Public API ------------------- #
__all__ = [
    "ingest_document",
    "with_correlation",
    "backfill_collection_filters",
    "backfill_collection_meta_vectors",
    "reap_stuck_jobs",
    "export_collection",
    "import_collection",
    "gc_expired_transfers",
    "reap_stuck_transfers",
    "gc_audit_log",
    "gc_job_history",
    "gc_idempotency_keys",
    "gc_artifact_cache",
    "gc_trace_payloads",
    "JobProgressRecorder",
    "CancellationGuard",
    "JobCancelledError",
]
