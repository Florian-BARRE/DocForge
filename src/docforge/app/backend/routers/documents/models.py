# ====== Code Summary ======
# Pydantic models for the documents router — the admission responses + the metadata value-edit.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field


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


class MetadataValuesPatch(BaseModel):
    """
    The metadata VALUES to write on a document (field_name → new value), the cheap value-edit.

    Attributes:
        values (dict[str, Any]): Map of metadata field name → new value. DOCUMENT-scope USER or
            GENERATED fields only; a chunk-scope or unknown field is rejected (422). A value's shape
            must match its field type (scalar, or a list for the *_list types).
    """

    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(
        min_length=1,
        description="Map of metadata field name → new value (document-scope fields only).",
    )


class MetadataUpdateResponse(BaseModel):
    """
    The result of a document metadata value edit.

    Attributes:
        updated_fields (list[str]): The field names whose values were written.
        reembedding (bool): True when a changed field feeds a named vector (semantic/lexical) and a
            re-embed job was enqueued.
        reembed_fields (list[str]): The changed fields that need their metadata vectors re-embedded.
        job_id (str | None): The enqueued re-embed job's id, or null when nothing needed re-embedding.
    """

    updated_fields: list[str] = Field(description="Field names whose values were written.")
    reembedding: bool = Field(
        description="A semantic/lexical field changed — a re-embed was queued."
    )
    reembed_fields: list[str] = Field(description="Changed fields needing a metadata re-embed.")
    job_id: str | None = Field(default=None, description="The re-embed job's UUID, or null.")


__all__ = [
    "UploadAccepted",
    "EnabledPatch",
    "DocumentEnabledResponse",
    "MetadataValuesPatch",
    "MetadataUpdateResponse",
]
