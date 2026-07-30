# ====== Code Summary ======
# The metagen-stage artefact: the DOCUMENT-scope generated metadata (chunk-scope values travel on
# each Chunk.generated_meta). Values are already coerced to their contract FieldType — the worker
# persists them relationally (document_metadata) without re-interpretation.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact


class GeneratedDocumentMeta(Artifact):
    """
    Document-scope generated metadata — one value per GENERATED/DOCUMENT contract field.

    Attributes:
        values (dict): Field name → coerced value (absent = the model could not provide a
            usable value; never a wrong-typed one).
    """

    values: dict[str, Any] = Field(default_factory=dict)


__all__ = ["GeneratedDocumentMeta"]
