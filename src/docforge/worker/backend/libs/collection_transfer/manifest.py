# ====== Code Summary ======
# The `.dcexport` bundle's typed contract: the `manifest.json` model (ExportManifest) and the
# `collection.json` model (CollectionContractModel), both Pydantic with ``extra="forbid"`` so a
# malformed or tampered bundle fails validation loudly instead of importing partial garbage.
# ``format_version`` is a real versioning seam: SUPPORTED_FORMAT_VERSIONS gates what this build can
# read, and the importer registry (see restore/importer.py) dispatches on it — V1 reads V1, and a
# future V2 migrator slots in without touching V1.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# The format versions THIS build can import. Start at 1; a V2 adds its number here + a migrator.
CURRENT_FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = frozenset({1})


class FileEntry(BaseModel):
    """One bundle file's integrity record — its in-tar path, sha256 and byte size."""

    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    size_bytes: int


class CollectionRef(BaseModel):
    """The exported collection's identity (its ORIGINAL id, purely informational on import)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class TransferCounts(BaseModel):
    """Per-domain row/object counts — a fast integrity + progress summary."""

    model_config = ConfigDict(extra="forbid")

    documents: int = 0
    pages: int = 0
    blocks: int = 0
    enrichments: int = 0
    chunks: int = 0
    entity_mentions: int = 0
    points: int = 0
    blobs: int = 0
    metadata_fields: int = 0


class ExportManifest(BaseModel):
    """The bundle's manifest.json — format seam, provenance, dimensions, counts and checksums."""

    model_config = ConfigDict(extra="forbid")

    format_version: int
    docforge_version: str
    created_at: str  # ISO-8601, stamped by the worker at assembly time
    collection: CollectionRef
    # The Qdrant dense vector size, fixed at first ``ensure``; the importer MUST recreate with it.
    dense_dim: int
    compression: str = "none"  # "none" | "zstd"
    counts: TransferCounts = Field(default_factory=TransferCounts)
    files: list[FileEntry] = Field(default_factory=list)


class ConfigVersionModel(BaseModel):
    """One appended config snapshot carried in collection.json (optional history)."""

    model_config = ConfigDict(extra="forbid")

    version: int
    config: dict
    note: str | None = None
    created_at: str | None = None


class CollectionContractModel(BaseModel):
    """The collection.json contract — everything needed to recreate the collection row + config."""

    model_config = ConfigDict(extra="forbid")

    name: str
    supported_formats: list[str]
    max_file_size_bytes: int
    job_timeout_seconds: float | None = None
    needs_reindex: bool = False
    pipeline: dict = Field(default_factory=dict)
    search: dict = Field(default_factory=dict)
    config_versions: list[ConfigVersionModel] = Field(default_factory=list)


def is_supported_version(format_version: int) -> bool:
    """Whether THIS build can import a bundle of the given format version."""
    return format_version in SUPPORTED_FORMAT_VERSIONS


__all__ = [
    "CURRENT_FORMAT_VERSION",
    "SUPPORTED_FORMAT_VERSIONS",
    "FileEntry",
    "CollectionRef",
    "TransferCounts",
    "ExportManifest",
    "ConfigVersionModel",
    "CollectionContractModel",
    "is_supported_version",
]
