# ====== Code Summary ======
# Request/response models for the pipeline design surface: the payload that opens the editor
# (palette + blob + described mirror) and the inspect round-trip the editor loops on.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.edit import EditOperation
from shared_libs.pipelines.ingest.stages import StageAction, StageView
from shared_libs.pipelines.introspection import ExploredNode, Palette
from shared_libs.pipelines.validation import ValidationIssue


class PipelineDesignResponse(BaseModel):
    """
    Everything the product UI needs to open the design surface in one call.

    The default payload is LEAN: family catalogue + blob + issues. The advanced blocks
    (``palette.run_inputs`` / ``mechanics`` / ``artefacts``) are only filled when the request
    asks for the full surface (``?full=true``); the described tree of a blob is served by the
    advanced ``/inspect`` and ``/edit`` endpoints, never here.

    Attributes:
        palette (Palette): Every available block (per family); advanced blocks when ``full``.
        blob (GroupNodeBlob): The editable pipeline — the single source of truth the UI mutates.
        issues (list[ValidationIssue]): Validation problems of the blob (empty when healthy).
    """

    palette: Palette
    blob: GroupNodeBlob
    issues: list[ValidationIssue] = Field(default_factory=list)


class InspectRequest(BaseModel):
    """The pipeline blob the UI is currently editing."""

    blob: GroupNodeBlob = Field(..., description="Serialised pipeline graph to inspect.")


class InspectResponse(BaseModel):
    """
    The described mirror of an edited pipeline.

    A structurally invalid graph is DATA for the editor (valid=false + issues), never an HTTP
    error; build_error is only set when the blob cannot even be built into a graph.

    Attributes:
        valid (bool): True when the graph built and has zero validation issues.
        issues (list[ValidationIssue]): Every problem found (code + location + message).
        explored (ExploredNode | None): The described tree; None when the build itself failed.
        build_error (str | None): Precise builder failure (unknown kind, invalid config…).
    """

    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    explored: ExploredNode | None = None
    build_error: str | None = None


class EditRequest(BaseModel):
    """A blob plus the ordered graph operations to apply to it server-side."""

    blob: GroupNodeBlob = Field(..., description="The pipeline blob the operations start from.")
    operations: list[EditOperation] = Field(
        default_factory=list, description="Ordered edit operations (add/remove/wire/insert/…)."
    )


class EditResponse(BaseModel):
    """
    The result of applying edit operations, then building + validating + describing the result.

    An impossible OPERATION is DATA, never an HTTP error: ``edit_error`` is set, the ORIGINAL blob
    is echoed back and ``valid`` is false. A successful apply mirrors ``/inspect`` — a merely
    invalid RESULT is still returned with its ``issues`` so the UI can show them. A result that
    cannot even be built (an invalid config from set_config/insert_fragment) is likewise surfaced
    through ``edit_error`` (the edit produced no buildable graph), with the edited blob echoed.

    Attributes:
        blob (GroupNodeBlob): The edited blob (or the original when an operation was impossible).
        valid (bool): True when the edited blob built and has zero validation issues.
        issues (list[ValidationIssue]): Every validation problem found in the edited graph.
        explored (ExploredNode | None): The described tree; None when apply or build failed.
        edit_error (str | None): Set when an operation was impossible, or the result was unbuildable.
    """

    blob: GroupNodeBlob
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    explored: ExploredNode | None = None
    edit_error: str | None = None


class StageViewRequest(BaseModel):
    """The blob to derive the simple stage view from."""

    blob: GroupNodeBlob = Field(..., description="Serialised pipeline graph to view as stages.")


class StageViewResponse(BaseModel):
    """
    The stage view of a blob — the full ordered skeleton PLUS its validity verdict.

    Validity is folded in so the product UI opens on ONE call (no priming ``/inspect``): a
    structurally broken blob is DATA (valid=false + issues), never an HTTP error, mirroring
    the inspect/edit contract.

    Attributes:
        stages (list[StageView]): The canonical stages in run order, greyed where disabled.
        valid (bool): True when the blob built and has zero validation issues.
        issues (list[ValidationIssue]): Every validation problem found (empty when healthy).
        build_error (str | None): Precise builder failure when the blob cannot even be built
            into a graph (issues are then unknowable and left empty).
    """

    stages: list[StageView]
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    build_error: str | None = None


class StageApplyRequest(BaseModel):
    """A blob plus one stage-level action to compile into a blob transformation."""

    blob: GroupNodeBlob = Field(..., description="The blob the action starts from.")
    action: StageAction = Field(
        ..., description="The stage action (toggle / set_provider / set_config / set_chain / set_stack)."
    )


class StageApplyResponse(BaseModel):
    """
    The result of compiling a stage action: the new blob, its stage view, validity and notices.

    Attributes:
        blob (GroupNodeBlob): The recompiled blob (always buildable — the assembler rewires it).
        stages (list[StageView]): The stage view of the recompiled blob, in run order.
        valid (bool): True when the blob built and has zero validation issues.
        issues (list[ValidationIssue]): Validation problems (e.g. a required config the user must
            still fill) — expected and shown, never fatal.
        notices (list[str]): What the compiler did beyond the literal action (dependency cascades,
            ignored no-ops).
        build_error (str | None): Set when the recompiled blob cannot build (a required config
            still empty) — fix-in-place data, never a 500.
    """

    build_error: str | None = None
    blob: GroupNodeBlob
    stages: list[StageView]
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)


class PipelineSurface(BaseModel):
    """
    One available pipeline design surface — the discovery unit a zero-hardcode UI starts from.

    Attributes:
        key (str): Stable pipeline identifier (e.g. ``"ingest"``).
        title (str): Human label.
        description (str): What this pipeline does.
        design_url (str): GET — the lean design payload (palette families + blob + issues);
            ``?full=true`` adds the advanced palette blocks (run_inputs, mechanics, artefacts).
        inspect_url (str): POST — advanced: blob in, validity + issues + described tree out.
        edit_url (str): POST — advanced: apply graph operations server-side (blob + operations
            in, healed blob + issues + described tree out); the healing semantics live next to
            the validator.
        stages_view_url (str | None): POST — the stage view of a blob + its validity (blob in,
            ordered stages + valid + issues out) — the product UI's one-call open. None when the
            pipeline has no stage rail (the stage layer is ingest-coupled today).
        stages_apply_url (str | None): POST — compile a stage action into the blob (blob + action
            in, recompiled blob + stage view + issues + notices out). None when unsupported.
    """

    key: str
    title: str
    description: str
    design_url: str
    inspect_url: str
    edit_url: str
    stages_view_url: str | None = None
    stages_apply_url: str | None = None


class PipelineIndexResponse(BaseModel):
    """The pipelines the backend serves — the UI's single bootstrap call."""

    pipelines: list[PipelineSurface] = Field(default_factory=list)


__all__ = [
    "PipelineDesignResponse",
    "InspectRequest",
    "InspectResponse",
    "EditRequest",
    "EditResponse",
    "StageViewRequest",
    "StageViewResponse",
    "StageApplyRequest",
    "StageApplyResponse",
    "PipelineSurface",
    "PipelineIndexResponse",
]
