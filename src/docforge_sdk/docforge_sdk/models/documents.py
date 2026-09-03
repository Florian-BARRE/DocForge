# ====== Code Summary ======
# Request/response models for the documents resource, mirrored field-for-field from the DocForge
# backend router models: the async-admission response and the searchability toggle contract.
# DocumentView is an SDK-only wrapper (no matching OpenAPI schema): the markdown/html document-view
# endpoints stream a raw text body with a Content-Type header rather than a JSON body, mirroring the
# blobs resource's BlobContent wrapper.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class UploadAccepted(BaseModel):
    """
    Response for an accepted upload — the ingestion runs asynchronously.

    Attributes:
        document_id (str): The admitted document (poll its ingestion via the job).
        job_id (str): The ingestion job driving status/progress ('' when duplicate).
        duplicate (bool): True when this exact content+pipeline was already ingested — the EXISTING
            document is returned and nothing is re-run.
    """

    document_id: str = Field(description="The admitted document's UUID.")
    job_id: str = Field(description="The ingestion job's UUID ('' when duplicate).")
    duplicate: bool = Field(default=False, description="Already ingested — nothing re-run.")


class EnabledPatch(BaseModel):
    """
    The desired searchability state for a document (the reversible toggle).

    Attributes:
        enabled (bool): True to make it searchable, False to hide it from search.
    """

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


class DocumentView(BaseModel):
    """
    A rendered document view's raw text plus its server-declared media type.

    Attributes:
        content (str): The rendered view body (markdown or HTML), verbatim.
        mime_type (str): The media type the server declared for the view.
    """

    content: str = Field(description="The rendered view body, verbatim.")
    mime_type: str = Field(description="The media type the server declared for the view.")


__all__ = ["UploadAccepted", "EnabledPatch", "DocumentEnabledResponse", "DocumentView"]
