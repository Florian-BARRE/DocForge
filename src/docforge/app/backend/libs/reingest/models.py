# ====== Code Summary ======
# Pydantic request/response models for the bulk re-ingest endpoint — co-located with the service
# that produces them (the health lib's models.py precedent). The request optionally selects an
# explicit document subset (omit → the whole collection); the response returns one job handle per
# enqueued run for the client to poll.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class BulkReingestRequest(BaseModel):
    """
    The re-run request over a collection's corpus (a full-pipeline re-ingest).

    Attributes:
        document_ids (list[str] | None): The explicit subset to re-run. Omit or null → EVERY
            document in the collection. An empty list is rejected (an ambiguous no-op).
    """

    document_ids: list[str] | None = Field(
        default=None,
        description="Explicit document UUIDs to re-run; omit for the whole collection.",
    )


class ReingestJobHandle(BaseModel):
    """
    One enqueued re-ingestion — the client polls the job for status/progress.

    Attributes:
        document_id (str): The document being re-ingested.
        job_id (str): The fresh ingestion job driving its lifecycle.
    """

    document_id: str = Field(description="The re-ingested document's UUID.")
    job_id: str = Field(description="The fresh ingestion job's UUID (poll this).")


class BulkReingestAccepted(BaseModel):
    """
    The accepted bulk re-run — the runs execute asynchronously (poll each job).

    Attributes:
        collection_id (str): The target collection.
        count (int): How many jobs were enqueued (= len(jobs)).
        jobs (list[ReingestJobHandle]): One handle per enqueued run.
    """

    collection_id: str = Field(description="The target collection's UUID.")
    count: int = Field(description="Number of jobs enqueued.")
    jobs: list[ReingestJobHandle] = Field(description="One handle per enqueued run.")


__all__ = ["BulkReingestRequest", "ReingestJobHandle", "BulkReingestAccepted"]
