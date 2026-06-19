# ====== Code Summary ======
# Request + response models for the collection configuration endpoints.
# The pipeline echoed in any response is credential-redacted (see PipelineConfig.redacted_dict).

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from libs.governance.config_validation import ConfigApplied, ConfigDocument
from libs.engine.pipeline_config import PipelineConfig

# ─────────────────────────── Requests ───────────────────────────


class ConfigUpdateRequest(BaseModel):
    """Partial config update — only provided keys replace existing values."""

    patch: dict[str, Any] = Field(default_factory=dict, description="Partial config document.")
    note: str | None = Field(default=None, description="Optional change note for the history.")


class ConfigRollbackRequest(BaseModel):
    """Target a previous config version to restore."""

    version: int = Field(..., ge=1, description="History version number to roll back to.")


# ─────────────────────────── Responses ───────────────────────────


class ConfigMetaField(BaseModel):
    """One metadata field of the collection schema."""

    field_name: str
    field_type: str
    required: bool
    filterable: bool
    lexical: bool
    semantic: bool
    enum_values: list[str] | None = None
    is_system: bool


class ConfigStateResponse(BaseModel):
    """The collection's full current configuration (identity + contract + pipeline + schema)."""

    id: str
    name: str
    pipeline_version: str
    needs_reindex: bool
    supported_formats: list[str]
    max_file_size_bytes: int
    locality_policy: str
    embedding_model: str
    unknown_field_policy: str
    pipeline: dict[str, Any] = Field(..., description="Pipeline config (credentials redacted).")
    metadata_fields: list[ConfigMetaField]
    created_at: datetime | None = Field(default=None, description="Creation timestamp (set on create).")
    applied: ConfigApplied | None = Field(
        default=None,
        description="Transparency envelope — what was provided vs defaulted, warnings, notes.",
    )

    @classmethod
    def from_collection(cls, collection: Any, applied: ConfigApplied | None = None) -> "ConfigStateResponse":
        """
        Build the full (redacted) config state from a persisted collection.

        Shared by create / state / update / rollback so every config response has one shape.

        Args:
            collection (Any): A CollectionModel with metadata_fields eagerly loaded.
            applied (ConfigApplied | None): Transparency envelope, when a caller action produced one.

        Returns:
            ConfigStateResponse: The redacted, resolved config state.
        """
        # 1. Canonical editable doc + redact pipeline credentials before echoing
        doc = ConfigDocument.from_collection(collection)
        redacted_pipeline = PipelineConfig.from_dict(doc["pipeline"]).redacted_dict()

        # 2. Assemble identity + state + contract + redacted pipeline + schema + transparency
        return cls(
            id=str(collection.id),
            name=collection.name,
            pipeline_version=collection.pipeline_version,
            needs_reindex=collection.needs_reindex,
            supported_formats=doc["supported_formats"],
            max_file_size_bytes=doc["max_file_size_bytes"],
            locality_policy=doc["locality_policy"],
            embedding_model=doc["embedding_model"],
            unknown_field_policy=doc["unknown_field_policy"],
            pipeline=redacted_pipeline,
            metadata_fields=doc["metadata_fields"],
            created_at=getattr(collection, "created_at", None),
            applied=applied,
        )


class ConfigSchemaResponse(BaseModel):
    """Metadata schema for this collection: system (auto-extracted) + custom (caller-provided)."""

    metadata_fields: list[ConfigMetaField]


class ConfigVersionSummary(BaseModel):
    """One entry in the config version history."""

    version: int
    pipeline_version: str
    note: str | None
    created_at: datetime


class ConfigHistoryResponse(BaseModel):
    """The config version history for a collection (newest first)."""

    collection_id: str
    total: int
    versions: list[ConfigVersionSummary]
