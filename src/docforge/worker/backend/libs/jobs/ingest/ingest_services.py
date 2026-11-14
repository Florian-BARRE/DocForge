# ====== Code Summary ======
# IngestServices — the worker services one ingest run needs (database façade, S3 handle, pipeline
# runner, runtime config, logger, worker id, default job timeout), gathered once from the worker's
# CONTEXT by the thin ``ingest_document`` entry and handed to IngestJob. The collaborators of the
# ``ingest`` package receive these values through their constructors and never import the worker
# CONTEXT themselves.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class IngestServices:
    """The injected services of one ingest (or replay) run.

    Attributes:
        database (Any): The worker's Database façade.
        s3 (Any): The worker's S3 handle (``client()`` context manager + ``bucket``).
        runner (Any): The PipelineRunner executing the graph.
        config (Any): The runtime config (``CONTEXT.RUNTIME_CONFIG``).
        logger (Any): The worker logger.
        worker_id (str): This worker's id (stamped on the claimed job).
        job_timeout_seconds (float): The worker's global default job timeout.
    """

    database: Any
    s3: Any
    runner: Any
    config: Any
    logger: Any
    worker_id: str
    job_timeout_seconds: float

    @classmethod
    def from_context(cls, context: Any) -> "IngestServices":
        """Read the services off the worker CONTEXT (the one place that touches it)."""
        return cls(
            database=context.database,
            s3=context.s3,
            runner=context.runner,
            config=context.RUNTIME_CONFIG,
            logger=context.logger,
            worker_id=context.worker_id,
            job_timeout_seconds=context.job_timeout_seconds,
        )


__all__ = ["IngestServices"]
