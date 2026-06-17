# ====== Code Summary ======
# ConfigApplied + ConfigExplainer — the transparency envelope echoed by every config-bearing
# endpoint (collection create / config update / rollback). It spells out exactly what the caller
# provided, what was filled from defaults, which system metadata fields were auto-injected,
# whether a reindex was triggered, and any non-blocking validation warnings — so the API is
# self-explanatory and a caller can verify nothing happened implicitly behind their back.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# Top-level editable keys of a config document (order = display order).
_EDITABLE_KEYS: list[str] = [
    "supported_formats", "max_file_size_bytes", "locality_policy",
    "embedding_model", "unknown_field_policy", "pipeline", "metadata_fields",
]
# Pipeline sub-sections reported individually as provided vs default.
_PIPELINE_SECTIONS: list[str] = ["parse", "enrich", "chunk", "embed"]


class AppliedIssue(BaseModel):
    """A single non-blocking validation warning surfaced to the caller."""

    code: str
    field: str
    message: str


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
        warnings (list[AppliedIssue]): Non-blocking validation warnings.
        notes (list[str]): Human-readable summary lines of what was applied.
    """

    provided: list[str] = Field(default_factory=list)
    defaulted: list[str] = Field(default_factory=list)
    pipeline: dict[str, str] = Field(default_factory=dict)
    metadata_fields: dict[str, int] = Field(default_factory=dict)
    overridden_system_fields: list[str] = Field(default_factory=list)
    needs_reindex: bool = False
    warnings: list[AppliedIssue] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConfigExplainer:
    """Static builder for the ConfigApplied transparency envelope."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConfigExplainer is a static-only class and cannot be instantiated.")

    @classmethod
    def build(
        cls,
        *,
        provided_keys: set[str],
        raw_pipeline: dict[str, Any] | None,
        resolved_doc: dict[str, Any],
        issues: list[dict[str, Any]],
        needs_reindex: bool,
        custom_field_names: list[str] | None = None,
    ) -> ConfigApplied:
        """
        Build the transparency envelope from the request inputs and the resolved document.

        Args:
            provided_keys (set[str]): Top-level config keys the caller explicitly supplied.
            raw_pipeline (dict | None): The pipeline dict as sent by the caller (pre-defaults).
            resolved_doc (dict): The fully resolved config document (defaults + merged schema).
            issues (list[dict]): Validator issues (warnings are surfaced, errors block upstream).
            needs_reindex (bool): Whether the change flags the collection for reindex.
            custom_field_names (list[str] | None): Field names the caller submitted (for override
                detection against system fields).

        Returns:
            ConfigApplied: The populated envelope.
        """
        # 1. Provided vs defaulted top-level keys
        provided = [k for k in _EDITABLE_KEYS if k in provided_keys]
        defaulted = [k for k in _EDITABLE_KEYS if k not in provided_keys]

        # 2. Per-section pipeline provenance
        raw_pipeline = raw_pipeline or {}
        pipeline = {s: ("provided" if s in raw_pipeline else "default") for s in _PIPELINE_SECTIONS}

        # 3. Metadata field accounting (system always auto-injected; rest are custom)
        fields = resolved_doc.get("metadata_fields", []) or []
        system_names = {f.get("field_name") for f in fields if f.get("is_system")}
        n_system = sum(1 for f in fields if f.get("is_system"))
        n_custom = sum(1 for f in fields if not f.get("is_system"))
        overridden = sorted(n for n in (custom_field_names or []) if n in system_names)

        # 4. Surface non-blocking warnings verbatim
        warnings = [
            AppliedIssue(code=i["code"], field=i.get("field", ""), message=i["message"])
            for i in issues if i.get("severity") == "warning"
        ]

        # 5. Human-readable summary
        notes: list[str] = []
        if defaulted:
            notes.append(f"Filled from defaults: {', '.join(defaulted)}.")
        default_sections = [s for s, v in pipeline.items() if v == "default"]
        if default_sections:
            notes.append(f"Pipeline sections left at defaults: {', '.join(default_sections)}.")
        notes.append(f"{n_system} system metadata fields auto-injected; {n_custom} custom field(s).")
        if overridden:
            notes.append(f"System field flags overridden: {', '.join(overridden)}.")
        if needs_reindex:
            notes.append("needs_reindex set — embedding model changed; re-embed required.")
        if warnings:
            notes.append(f"{len(warnings)} non-blocking warning(s) — see 'warnings'.")

        return ConfigApplied(
            provided=provided,
            defaulted=defaulted,
            pipeline=pipeline,
            metadata_fields={"system": n_system, "custom": n_custom},
            overridden_system_fields=overridden,
            needs_reindex=needs_reindex,
            warnings=warnings,
            notes=notes,
        )
