# ====== Code Summary ======
# SourceDocument — the artefact the pipeline RUN starts from: the uploaded file's bytes, its
# original filename, and the metadata the caller declared at upload. It is a run input (bound via
# FromRunInput); the admit node validates it against the CollectionContract before anything is
# spent on it.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact


class SourceDocument(Artifact):
    """An uploaded source — bytes, filename, and the caller-declared metadata."""

    filename: str = Field(description="Original filename (its extension hints the format).")
    content: bytes = Field(description="The raw uploaded bytes.")
    declared_meta: dict[str, Any] = Field(
        default_factory=dict, description="Metadata values the caller supplied at upload."
    )


__all__ = ["SourceDocument"]
