# ====== Code Summary ======
# Response model for the blobs resource. A blob endpoint streams raw bytes with a registered media
# type rather than a JSON body, so BlobContent is an SDK-only wrapper (no matching OpenAPI schema)
# pairing the fetched bytes with the server-declared mime type.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class BlobContent(BaseModel):
    """
    A fetched blob's raw bytes plus its server-registered media type.

    Attributes:
        content (bytes): The raw blob bytes, verbatim.
        mime_type (str): The media type the server registered for the blob.
    """

    model_config = {"arbitrary_types_allowed": True}

    content: bytes = Field(description="The raw blob bytes, verbatim.")
    mime_type: str = Field(description="The media type the server registered for the blob.")


__all__ = ["BlobContent"]
