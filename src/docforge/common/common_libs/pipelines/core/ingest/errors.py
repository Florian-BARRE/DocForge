# ====== Code Summary ======
# IngestError — the root of the ingest pipeline's error family. Every stage/step error of this
# pipeline ultimately specialises the generic PipelineError; this gives the pipeline a single
# top-level error type for callers to catch.

# ====== Internal Project Imports ======
from common_libs.pipelines import PipelineError


class IngestError(PipelineError):
    """Root error for the ingest pipeline."""

    code = "ingest_pipeline_error"
    description = "The document could not be ingested (a stage of the ingest pipeline failed)."


__all__ = ["IngestError"]
