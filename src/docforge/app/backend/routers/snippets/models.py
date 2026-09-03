# ====== Code Summary ======
# The granular collection-config SNIPPET contract: a small, portable, secret-masked, versioned
# wrapper around ONE slice of a collection's configuration (its ingest pipeline blob, its search blob,
# or its metadata schema). Unlike the whole-collection `.dcexport` bundle (async, worker-built, carries
# data), a snippet is synchronous config-only and is exported/imported over plain JSON. ``format_version``
# is a real seam (mirrors the export manifest): SUPPORTED_SNIPPET_VERSIONS gates what this build reads.

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# The snippet format versions THIS build can import. Start at 1; a V2 adds its number + a migrator.
CURRENT_SNIPPET_VERSION = 1
SUPPORTED_SNIPPET_VERSIONS = frozenset({1})
# File extension the frontend/SDK saves a snippet under — deliberately DISTINCT from `.dcexport`
# (the whole-collection bundle) so the two are never confused on disk or in an importer.
SNIPPET_FILE_EXTENSION = ".dfsnippet"

# The three config slices a snippet can carry.
SnippetKind = Literal["pipeline", "search", "schema"]


def is_supported_snippet_version(format_version: int) -> bool:
    """Whether THIS build can import a snippet of the given format version."""
    return format_version in SUPPORTED_SNIPPET_VERSIONS


class CollectionSnippet(BaseModel):
    """
    A portable, secret-masked, versioned wrapper around one collection-config slice.

    The ``body`` shape depends on ``kind``: for ``pipeline`` / ``search`` it is the graph blob (with
    every provider ``api_key`` masked); for ``schema`` it is ``{"fields": [FieldSpecModel, ...]}``.

    Attributes:
        kind (SnippetKind): Which config slice this snippet carries.
        format_version (int): The snippet format version (gated on import).
        docforge_version (str): The producing build's version (provenance, informational).
        body (dict): The slice payload (see the kind-specific shape above).
    """

    model_config = ConfigDict(extra="forbid")

    kind: SnippetKind = Field(description="Which config slice this snippet carries.")
    format_version: int = Field(description="The snippet format version (gated on import).")
    docforge_version: str = Field(
        description="Producing build version (provenance, informational)."
    )
    body: dict[str, Any] = Field(description="The slice payload (blob dict, or {'fields': [...]}).")


class SnippetImportResult(BaseModel):
    """The outcome of applying a config snippet to a collection."""

    collection_id: str = Field(description="The target collection's UUID.")
    kind: SnippetKind = Field(description="The config slice that was applied.")
    needs_reindex: bool = Field(
        description="Whether applying this snippet flags a reindex requirement (embed-space or "
        "searchable-schema change); always false for a search snippet."
    )


__all__ = [
    "CURRENT_SNIPPET_VERSION",
    "SUPPORTED_SNIPPET_VERSIONS",
    "SNIPPET_FILE_EXTENSION",
    "SnippetKind",
    "is_supported_snippet_version",
    "CollectionSnippet",
    "SnippetImportResult",
]
