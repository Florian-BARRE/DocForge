# ====== Code Summary ======
# Response models of the versioned config history — GET /collections/{id}/config-versions (page),
# /config-versions/{version} (one masked snapshot), /config-versions/diff (structured masked diff) and
# POST /config-versions/{version}/restore. Every config value served here is secret-MASKED.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ConfigVersionSummary(BaseModel):
    """One entry of a collection's config history (no config body)."""

    version: int = Field(..., description="Per-collection version number (1 = creation).")
    created_at: datetime = Field(..., description="When this version was written.")
    note: str | None = Field(default=None, description="The note stored with the version.")
    author_label: str | None = Field(
        default=None,
        description='Who wrote it: "<key name> (<key prefix>)" (the root token reads "root (df_…)"), '
        'or "anonymous" (auth off); null = '
        "unknown (written before authorship was recorded, or a system write such as an import).",
    )
    author_key_id: str | None = Field(
        default=None, description="The authoring API key id (null once that key is deleted)."
    )
    changes: list[str] = Field(
        default_factory=list,
        description='What changed vs the previous version: "pipeline:<node id>", "pipeline:(graph)" '
        '(transitions/bindings), "search". Empty for version 1 or a no-op write.',
    )


class ConfigVersionListResponse(BaseModel):
    """One newest-first page of a collection's config history."""

    collection_id: str
    total: int = Field(..., description="Number of versions in the whole history.")
    limit: int
    offset: int
    items: list[ConfigVersionSummary]


class ConfigVersionDetail(ConfigVersionSummary):
    """One config version with its {pipeline, search} snapshot — every provider secret masked."""

    config: dict[str, Any] = Field(
        ..., description="The snapshot {pipeline, search}; secrets replaced by the mask marker."
    )


class ConfigDiffEntry(BaseModel):
    """One changed path between two versions (values masked)."""

    path: str = Field(
        ...,
        description="JSON-pointer style path; graph nodes are keyed by id, e.g. "
        '"/pipeline/nodes/parse/config/max_pages".',
    )
    op: Literal["added", "removed", "changed"]
    before: Any = Field(default=None, description="The masked value in `from` (absent → null).")
    after: Any = Field(default=None, description="The masked value in `to` (absent → null).")


class ConfigVersionDiffResponse(BaseModel):
    """The structured diff from one config version to another (secrets always masked)."""

    collection_id: str
    from_version: int
    to_version: int
    changes: list[ConfigDiffEntry]


class ConfigVersionRestoreResponse(BaseModel):
    """The outcome of restoring a config version (always a NEW version, never a history rewrite)."""

    collection_id: str
    restored_from: int = Field(..., description="The version whose config was re-applied.")
    version: int = Field(..., description='The new version written (note "restore of v{N}").')
    needs_reindex: bool = Field(
        ..., description="The collection's derived reindex flag after the restore."
    )
