# ====== Code Summary ======
# Response models for the pipeline design surface, mirrored field-for-field from the DocForge backend
# router models. The graph JSON is OPAQUE to the SDK: every payload the engine owns (blob, palette,
# explored tree, issues, stages) is typed as ``dict``/``list[dict]``; only the stable ENVELOPE fields
# (valid / build_error / notices / the surface URLs) carry precise types.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class PipelineSurface(BaseModel):
    """
    One available pipeline design surface — the discovery unit a zero-hardcode UI starts from.

    Attributes:
        key (str): Stable pipeline identifier (e.g. ``"ingest"``).
        title (str): Human label.
        description (str): What this pipeline does.
        design_url (str): GET — the lean design payload.
        inspect_url (str): POST — blob in, validity + issues + described tree out.
        edit_url (str): POST — apply graph operations server-side.
        stages_view_url (str | None): POST — the stage view of a blob (None when unsupported).
        stages_apply_url (str | None): POST — compile a stage action (None when unsupported).
    """

    key: str = Field(description="Stable pipeline identifier (e.g. 'ingest').")
    title: str = Field(description="Human label.")
    description: str = Field(description="What this pipeline does.")
    design_url: str = Field(description="GET — the lean design payload.")
    inspect_url: str = Field(description="POST — validity + issues + described tree.")
    edit_url: str = Field(description="POST — apply graph operations server-side.")
    stages_view_url: str | None = Field(
        default=None, description="POST — the stage view of a blob (None when unsupported)."
    )
    stages_apply_url: str | None = Field(
        default=None, description="POST — compile a stage action (None when unsupported)."
    )


class PipelineIndexResponse(BaseModel):
    """
    The pipelines the backend serves — the UI's single bootstrap call.

    Attributes:
        pipelines (list[PipelineSurface]): One entry per available design surface.
    """

    pipelines: list[PipelineSurface] = Field(
        default_factory=list, description="One entry per available design surface."
    )


class PipelineDesignResponse(BaseModel):
    """
    Everything the product UI needs to open the design surface in one call.

    Attributes:
        palette (dict[str, Any]): Every available block (per family); OPAQUE engine JSON.
        blob (dict[str, Any]): The editable pipeline graph; OPAQUE engine JSON.
        issues (list[dict[str, Any]]): Validation problems of the blob (empty when healthy).
    """

    palette: dict[str, Any] = Field(description="Available blocks per family (opaque engine JSON).")
    blob: dict[str, Any] = Field(description="The editable pipeline graph (opaque engine JSON).")
    issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Validation problems of the blob (opaque; empty = healthy)."
    )


class InspectResponse(BaseModel):
    """
    The described mirror of an edited pipeline.

    Attributes:
        valid (bool): True when the graph built and has zero validation issues.
        issues (list[dict[str, Any]]): Every problem found (opaque engine JSON).
        explored (dict[str, Any] | None): The described tree; None when the build failed.
        build_error (str | None): Precise builder failure (unknown kind, invalid config…).
    """

    valid: bool = Field(description="True when the graph built and has zero validation issues.")
    issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Every problem found (opaque engine JSON)."
    )
    explored: dict[str, Any] | None = Field(
        default=None, description="The described tree (opaque); None when the build failed."
    )
    build_error: str | None = Field(
        default=None, description="Precise builder failure (unknown kind, invalid config…)."
    )


class EditResponse(BaseModel):
    """
    The result of applying edit operations, then building + validating + describing the result.

    Attributes:
        blob (dict[str, Any]): The edited blob (or the original when an operation was impossible).
        valid (bool): True when the edited blob built and has zero validation issues.
        issues (list[dict[str, Any]]): Every validation problem found (opaque engine JSON).
        explored (dict[str, Any] | None): The described tree; None when apply or build failed.
        edit_error (str | None): Set when an operation was impossible or the result was unbuildable.
    """

    blob: dict[str, Any] = Field(description="The edited blob (opaque engine JSON).")
    valid: bool = Field(description="True when the edited blob built and has zero issues.")
    issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Every validation problem found (opaque engine JSON)."
    )
    explored: dict[str, Any] | None = Field(
        default=None, description="The described tree (opaque); None when apply/build failed."
    )
    edit_error: str | None = Field(
        default=None, description="Set when an operation was impossible or the result unbuildable."
    )


class StageViewResponse(BaseModel):
    """
    The stage view of a blob — the full ordered skeleton PLUS its validity verdict.

    Attributes:
        stages (list[dict[str, Any]]): The canonical stages in run order (opaque engine JSON).
        valid (bool): True when the blob built and has zero validation issues.
        issues (list[dict[str, Any]]): Every validation problem found (opaque engine JSON).
        build_error (str | None): Precise builder failure when the blob cannot even be built.
    """

    stages: list[dict[str, Any]] = Field(
        description="The canonical stages in run order (opaque engine JSON)."
    )
    valid: bool = Field(description="True when the blob built and has zero validation issues.")
    issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Every validation problem found (opaque engine JSON)."
    )
    build_error: str | None = Field(
        default=None, description="Precise builder failure when the blob cannot even be built."
    )


class StageApplyResponse(BaseModel):
    """
    The result of compiling a stage action: the new blob, its stage view, validity and notices.

    Attributes:
        blob (dict[str, Any]): The recompiled blob (always buildable; opaque engine JSON).
        stages (list[dict[str, Any]]): The stage view of the recompiled blob, in run order.
        valid (bool): True when the blob built and has zero validation issues.
        issues (list[dict[str, Any]]): Validation problems — expected and shown, never fatal.
        notices (list[str]): What the compiler did beyond the literal action.
        build_error (str | None): Set when the recompiled blob cannot build — fix-in-place data.
    """

    blob: dict[str, Any] = Field(description="The recompiled blob (opaque engine JSON).")
    stages: list[dict[str, Any]] = Field(
        description="The stage view of the recompiled blob, in run order (opaque engine JSON)."
    )
    valid: bool = Field(description="True when the blob built and has zero validation issues.")
    issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Validation problems — expected and shown, never fatal."
    )
    notices: list[str] = Field(
        default_factory=list, description="What the compiler did beyond the literal action."
    )
    build_error: str | None = Field(
        default=None, description="Set when the recompiled blob cannot build — fix-in-place data."
    )


__all__ = [
    "PipelineSurface",
    "PipelineIndexResponse",
    "PipelineDesignResponse",
    "InspectResponse",
    "EditResponse",
    "StageViewResponse",
    "StageApplyResponse",
]
