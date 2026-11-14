# ====== Code Summary ======
# RehydratedJob — everything the Rehydrator loads for one run (document + collection rows, the
# collection's metadata schema, the run input, the contract, the normalized blob, the wall-clock job
# timeout and the effective trace level). It doubles as the replay run's input: ReplayRun consumes the
# same fields, so both modes share ONE shape (ReplayInputs below adds only the job id and the stage).

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.engine import TraceLevel
from shared_libs.public_models import CollectionContract, SourceDocument


@dataclass(slots=True)
class RehydratedJob:
    """The inputs of one run, loaded from the rows (and S3, for a full run)."""

    document: Any
    collection: Any
    schema: list[Any]
    source: SourceDocument
    contract: CollectionContract
    blob: dict
    timeout_seconds: float
    trace_level: TraceLevel


@dataclass(slots=True)
class ReplayInputs:
    """Everything ingest_document already rehydrated, handed to the replay run."""

    job_id: uuid.UUID
    document: Any
    collection: Any
    schema: list[Any]
    source: SourceDocument
    contract: CollectionContract
    blob: dict
    stage: str
    timeout_seconds: float
    trace_level: TraceLevel

    @classmethod
    def from_rehydrated(
        cls, job_id: uuid.UUID, rehydrated: RehydratedJob, stage: str
    ) -> "ReplayInputs":
        """Build the replay run's input from a rehydrated job and the stage to replay from."""
        return cls(
            job_id=job_id,
            document=rehydrated.document,
            collection=rehydrated.collection,
            schema=rehydrated.schema,
            source=rehydrated.source,
            contract=rehydrated.contract,
            blob=rehydrated.blob,
            stage=stage,
            timeout_seconds=rehydrated.timeout_seconds,
            trace_level=rehydrated.trace_level,
        )


__all__ = ["RehydratedJob", "ReplayInputs"]
