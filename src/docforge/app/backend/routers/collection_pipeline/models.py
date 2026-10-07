# ====== Code Summary ======
# Request/response models of the collection-scoped stage edit — POST
# /collections/{id}/pipeline/stages/apply. The caller sends ONE stage action; the server reads the
# collection's stored pipeline, applies it, validates it and persists it. The response is the redacted
# stage view of the result (never the blob, never a secret) plus validity, notices and the persist
# verdict — so an LLM edits a collection's pipeline without ever round-tripping the full blob.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest.stages import StageAction, StageView
from shared_libs.pipelines.validation import ValidationIssue


class CollectionStageApplyRequest(BaseModel):
    """One stage action to apply to a collection's stored ingestion pipeline (persisted on success)."""

    model_config = ConfigDict(extra="forbid")

    action: StageAction = Field(
        ...,
        description="The stage action (enable_stage / disable_stage / set_provider / set_config / "
        "set_chain / set_stack). Prefer set_config with mode='merge' to change single keys: every "
        "other key, secrets included, is kept.",
    )
    note: str | None = Field(
        default=None,
        description="Note stored on the config-version snapshot (defaults to the action summary).",
    )


class CollectionStageApplyResponse(BaseModel):
    """
    The outcome of a collection-scoped stage action.

    Attributes:
        collection_id (str): The edited collection.
        persisted (bool): True when the new pipeline was stored (a new config version written).
        needs_reindex (bool): The collection's derived reindex flag after the write.
        stages (list[StageView]): The redacted stage view of the result (stored, or the rejected
            candidate when ``persisted`` is false).
        valid (bool): True when the resulting pipeline built and has zero validation issues.
        issues (list[ValidationIssue]): Validation problems (a required config still empty…).
        notices (list[str]): What the compiler did beyond the literal action, plus why nothing was
            persisted when that is the case.
        build_error (str | None): Precise builder failure when the result cannot build.
    """

    collection_id: str = Field(description="The edited collection.")
    persisted: bool = Field(
        description="True when the new pipeline was stored (a config version was written); false "
        "when the result is invalid or the action changed nothing."
    )
    needs_reindex: bool = Field(
        default=False,
        description="The collection's derived reindex flag after the write (embed-space change).",
    )
    stages: list[StageView] = Field(
        description="The redacted stage view of the resulting pipeline, in run order."
    )
    valid: bool = Field(description="True when the result built and has zero validation issues.")
    issues: list[ValidationIssue] = Field(
        default_factory=list, description="Validation problems of the result (empty when healthy)."
    )
    notices: list[str] = Field(
        default_factory=list,
        description="Compiler notices (cascades, ignored no-ops) and the reason nothing was stored.",
    )
    build_error: str | None = Field(
        default=None, description="Builder failure when the result cannot build (not persisted)."
    )


__all__ = ["CollectionStageApplyRequest", "CollectionStageApplyResponse"]
