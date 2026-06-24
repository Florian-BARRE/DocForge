# ====== Code Summary ======
# ConfigApplied — the transparency envelope echoed by every config-bearing endpoint
# (collection create / config update / rollback). It spells out exactly what the caller
# provided, what was filled from defaults, which system metadata fields were injected,
# whether a reindex was triggered, and any non-blocking validation warnings.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .applied_issue import AppliedIssue


class ConfigApplied(BaseModel):
    """
    Transparency envelope describing how a config request was resolved.

    Attributes:
        provided (list[str]): Top-level keys the caller explicitly sent.
        defaulted (list[str]): Editable keys filled from defaults (caller did not send them).
        pipeline (dict[str, str]): Per stage section → ``"provided"`` or ``"default"``.
        metadata_fields (dict[str, int]): Counts — ``system`` injected, ``custom`` added.
        overridden_system_fields (list[str]): System fields whose flags the caller overrode.
        needs_reindex (bool): Whether this change flagged the collection for reindex.
        reindex_reasons (list[str]): Exact, human-readable reasons the change requires a
            reindex (empty when the change was non-critical — e.g. search config or a
            non-searchable metadata field).
        warnings (list[AppliedIssue]): Non-blocking validation warnings.
        notes (list[str]): Human-readable summary lines of what was applied.
    """

    provided: list[str] = Field(default_factory=list)
    defaulted: list[str] = Field(default_factory=list)
    pipeline: dict[str, str] = Field(default_factory=dict)
    metadata_fields: dict[str, int] = Field(default_factory=dict)
    overridden_system_fields: list[str] = Field(default_factory=list)
    needs_reindex: bool = False
    reindex_reasons: list[str] = Field(default_factory=list)
    warnings: list[AppliedIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
