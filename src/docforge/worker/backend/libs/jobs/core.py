# ====== Code Summary ======
# The ingest_document arq task — the worker's whole job, in pipeline order: mark the job running,
# rehydrate the inputs (document row + original bytes from S3 + the collection's contract and
# pipeline blob), run the pipeline (fresh input, live progress), translate the delivery, persist
# through the façade (S3 → Postgres one-tx → Qdrant), close the job. Any failure marks BOTH the
# document and the job failed with the error in clear (a REPLAY failure fails only the job: the
# document keeps its status + gets a warning, its previous content still served), then re-raises.
# This module is only the thin arq entry: the run itself lives in the ``ingest`` package (IngestJob and
# its collaborators); here the worker CONTEXT is read once and injected.

# ====== Standard Library Imports ======
from typing import Any

# ====== Local Project Imports ======
from persistence import RunTranslator  # noqa: F401 - LEGACY-SEAM: patched through this module by tests
from runner.cache import StageCacheHook

# ====== Internal Project Imports (worker) ======
from backend.context import CONTEXT

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import BlobNormalizer  # noqa: F401 - LEGACY-SEAM: test patch seam

# ====== Local Project Imports ======
from .ingest import IngestJob, IngestServices
from .replay import ReplayRun


async def ingest_document(
    ctx: dict[str, Any], document_id: str, job_id: str, force: bool = False
) -> None:
    """
    Execute one ingestion end to end: rehydrate → run → translate → persist.

    Args:
        ctx (dict): arq's context dict (``job_try`` is the attempt counter).
        document_id (str): The admitted document's UUID (the queue carries ids only).
        job_id (str): The job row driving the lifecycle/status.
        force (bool): When True, build NO stage-cache hook — a full recompute that reads nothing
            from and writes nothing to the artifact cache (the reingest ``force=true`` path).
    """
    job = IngestJob(
        IngestServices.from_context(CONTEXT),
        replay_run=ReplayRun,
        cache_hook_factory=StageCacheHook,
    )
    await job.execute(ctx, document_id, job_id, force)


__all__ = ["ingest_document"]
