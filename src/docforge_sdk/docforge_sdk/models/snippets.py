# ====== Code Summary ======
# Request/response models for the granular collection config-SNIPPET endpoints, mirrored field-for-
# field from the DocForge backend (app/backend/routers/snippets/models.py). Unlike the whole-collection
# `.dcexport` bundle (async, worker-built, carries data), a snippet is a small, SYNCHRONOUS, config-only
# wrapper around ONE slice of a collection's configuration (its ingest pipeline blob, its search blob,
# or its metadata schema) — secret-masked and format-versioned. ``SNIPPET_FILE_EXTENSION`` (``.dfsnippet``)
# is deliberately distinct from ``.dcexport`` so the two are never confused on disk.

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# File extension a snippet is saved under — distinct from the whole-collection `.dcexport` bundle.
SNIPPET_FILE_EXTENSION = ".dfsnippet"

# The three config slices a snippet can carry.
SnippetKind = Literal["pipeline", "search", "schema"]


class CollectionSnippet(BaseModel):
    """
    A portable, secret-masked, versioned wrapper around one collection-config slice.

    The ``body`` shape depends on ``kind``: for ``pipeline`` / ``search`` it is the graph blob (with
    every provider ``api_key`` masked); for ``schema`` it is ``{"fields": [FieldSpec, ...]}``.

    Attributes:
        kind (SnippetKind): Which config slice this snippet carries.
        format_version (int): The snippet format version (gated on import).
        docforge_version (str): The producing build's version (provenance, informational).
        body (dict[str, Any]): The slice payload (see the kind-specific shape above).
    """

    kind: SnippetKind = Field(description="Which config slice this snippet carries.")
    format_version: int = Field(description="The snippet format version (gated on import).")
    docforge_version: str = Field(description="Producing build version (provenance, informational).")
    body: dict[str, Any] = Field(description="The slice payload (blob dict, or {'fields': [...]}).")


class SnippetImportResult(BaseModel):
    """
    The outcome of applying a config snippet to a collection.

    Attributes:
        collection_id (str): The target collection's UUID.
        kind (SnippetKind): The config slice that was applied.
        needs_reindex (bool): Whether applying this snippet flags a reindex requirement (embed-space
            or searchable-schema change); always false for a search snippet.
    """

    collection_id: str = Field(description="The target collection's UUID.")
    kind: SnippetKind = Field(description="The config slice that was applied.")
    needs_reindex: bool = Field(
        description="Whether applying this snippet flags a reindex requirement (embed-space or "
        "searchable-schema change); always false for a search snippet."
    )


__all__ = ["SNIPPET_FILE_EXTENSION", "SnippetKind", "CollectionSnippet", "SnippetImportResult"]
