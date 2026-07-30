# ====== Code Summary ======
# The clean transfer type for the object store: an `S3Object` bundles a key, its bytes and a content
# type. The Database façade builds these (the key is the blob's content hash) and hands them to the
# S3 apis for a batch put — so callers never juggle raw put_object kwargs.

# ====== Standard Library Imports ======
from dataclasses import dataclass


@dataclass(slots=True)
class S3Object:
    """One object to store: its key (the blob content hash), its bytes and its content type."""

    key: str
    data: bytes
    content_type: str = "application/octet-stream"


__all__ = ["S3Object"]
