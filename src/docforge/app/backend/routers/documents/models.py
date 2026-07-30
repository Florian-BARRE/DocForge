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


class EnabledPatch(BaseModel):
    """The desired searchability state for a document or chunk (the reversible toggle)."""

    enabled: bool = Field(description="True to make it searchable, False to hide it from search.")


class DocumentEnabledResponse(BaseModel):
    """
    The state of a document after toggling its searchability.

    Attributes:
        document_id (str): The toggled document.
        enabled (bool): Its new searchability state.
    """

    document_id: str = Field(description="The toggled document's UUID.")
    enabled: bool = Field(description="The new searchability state.")


__all__ = ["UploadAccepted", "EnabledPatch", "DocumentEnabledResponse"]
