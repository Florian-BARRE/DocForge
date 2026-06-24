# ====== Code Summary ======
# Response models for document file artefacts: pre-signed URLs.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class PresignedUrlResponse(BaseModel):
    """A time-limited object-store URL for downloading a document artefact."""

    url: str = Field(..., description="Pre-signed GET URL (expires in 1 hour).")
    expires_in: int = Field(default=3600, description="URL validity in seconds.")
