# ====== Code Summary ======
# Pydantic models for the documents router — the admission responses.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class UploadAccepted(BaseModel):
    """
    Response for an accepted upload — the ingestion runs asynchronously.

    Attributes:
        document_id (str): The admitted document (poll its ingestion via the job).
        job_id (str): The ingestion job driving status/progress.
        duplicate (bool): True when this exact content+pipeline was already ingested —
            the EXISTING document is returned and nothing is re-run.
    """

    document_id: str = Field(description="The admitted document's UUID.")
    job_id: str = Field(description="The ingestion job's UUID ('' when duplicate).")
    duplicate: bool = Field(default=False, description="Already ingested — nothing re-run.")


__all__ = ["UploadAccepted"]
