# ====== Code Summary ======
# IngestStageError — the base error for every stage of the ingest pipeline. Concrete stages (and
# their step errors) sit under it, so the feedback tree keeps a coherent ingest error family.

# ====== Internal Project Imports ======
from common_libs.pipelines import StageError


class IngestStageError(StageError):
    """Base for failures raised within a stage of the ingest pipeline."""

    code = "ingest_stage_error"
    description = "A stage of the ingest pipeline failed."


__all__ = ["IngestStageError"]
