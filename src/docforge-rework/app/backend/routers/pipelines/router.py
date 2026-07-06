# ====== Code Summary ======
# Route definitions for the pipeline design surface. Product path: the lean design GET (palette
# families + blob) and the stage endpoints (/stages/view with folded validity, /stages/apply).
# Advanced, headless path: ?full=true (full palette), /inspect and /edit (described tree + graph
# operations). The UI carries zero hardcoded pipeline knowledge — everything it renders comes
# from these endpoints.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError
from shared_libs.pipelines.edit import EditError
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import StageViewer, StateReader
from shared_libs.pipelines.introspection import PipelineExplorer

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors
from .models import (
    EditRequest,
    EditResponse,
    InspectRequest,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyRequest,
    StageApplyResponse,
    StageViewRequest,
    StageViewResponse,
)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=PipelineIndexResponse)
@auto_handle_errors
async def list_pipeline_surfaces() -> PipelineIndexResponse:
    """
    Discover the available pipeline design surfaces — the UI's single bootstrap call.

    Returns:
        PipelineIndexResponse: One entry per pipeline, each with its design/inspect URLs.
    """
    # 1. One entry per pipeline the backend serves (the search pipeline will join later).
    return PipelineIndexResponse(
        pipelines=[
            PipelineSurface(
                key="ingest",
                title="Ingestion pipeline",
                description=(
                    "Document intake to indexed chunks: intake, parse, per-figure enrichment, "
                    "chunking, contextualization, metadata generation and embedding."
                ),
                design_url="/api/v1/pipelines/ingest",
                inspect_url="/api/v1/pipelines/ingest/inspect",
                edit_url="/api/v1/pipelines/ingest/edit",
                stages_view_url="/api/v1/pipelines/ingest/stages/view",
                stages_apply_url="/api/v1/pipelines/ingest/stages/apply",
            )
        ]
    )


@router.get("/ingest", response_model=PipelineDesignResponse)
@auto_handle_errors
async def get_ingest_pipeline_design(full: bool = False) -> PipelineDesignResponse:
    """
    Open the ingestion pipeline design surface: palette + default blob + its issues.

    The default payload is lean — exactly what the product stage rail consumes (families +
    blob). ``?full=true`` upgrades the SAME payload with the advanced palette blocks
    (run_inputs, mechanics, artefacts) for headless graph-level tooling; the described tree
    of a blob is served by ``/inspect`` and ``/edit``.

    Args:
        full (bool): Query flag — when true, fill the advanced palette blocks.

    Returns:
        PipelineDesignResponse: The blocks catalogue, the editable blob and any validation
        issues (empty for the stock pipeline).
    """
    # 1. The editable truth — the default topology (per-collection blobs come later).
    blob = IngestPipeline.default_blob()

    # 2. Build transiently, only to validate — instances die with the request.
    group = CONTEXT.pipeline_builder.build(blob)
    issues = CONTEXT.graph_validator.validate(group)

    # 3. One payload; the product UI needs nothing else to construct itself.
    return PipelineDesignResponse(
        palette=IngestPipeline.palette(full=full),
        blob=blob,
        issues=issues,
    )


@router.post("/ingest/inspect", response_model=InspectResponse)
@auto_handle_errors
async def inspect_ingest_pipeline(request: InspectRequest) -> InspectResponse:
    """
    Build + validate + describe an edited pipeline blob — the editor's feedback loop.

    Returns:
        InspectResponse: valid flag, every validation issue, and the described tree.
    """
    # 1. Rebuild the live graph; a malformed blob is editor DATA, not an HTTP error.
    try:
        group = CONTEXT.pipeline_builder.build(request.blob)
    except BuildError as exc:
        return InspectResponse(valid=False, build_error=str(exc))

    # 2. Collect ALL validation issues (the validator never stops at the first one).
    issues = CONTEXT.graph_validator.validate(group)

    # 3. Describe the built tree so the UI re-renders from the backend's truth.
    return InspectResponse(
        valid=not issues,
        issues=issues,
        explored=PipelineExplorer.explore(group),
    )


@router.post("/ingest/edit", response_model=EditResponse)
@auto_handle_errors
async def edit_ingest_pipeline(request: EditRequest) -> EditResponse:
    """
    Apply graph operations to a blob server-side, then build + validate + describe the result.

    The editing/healing semantics live here, next to the invariants, so no client re-implements
    them. An impossible operation is DATA (edit_error set, original blob echoed, valid=false),
    never a 500; a merely invalid result comes back with its issues, exactly like /inspect.

    Returns:
        EditResponse: the edited blob, its validity, every issue, the described tree, edit_error.
    """
    # 1. Apply the operations to a deep copy; an impossible op is editor DATA, not an HTTP error.
    try:
        edited = CONTEXT.graph_editor.apply(request.blob, request.operations)
    except EditError as exc:
        return EditResponse(blob=request.blob, valid=False, edit_error=str(exc))

    # 2. Rebuild the edited blob; an unbuildable RESULT (a bad config) is surfaced, not raised.
    try:
        group = CONTEXT.pipeline_builder.build(edited)
    except BuildError as exc:
        return EditResponse(blob=edited, valid=False, edit_error=str(exc))

    # 3. Collect ALL validation issues and describe the tree — same feedback loop as /inspect.
    issues = CONTEXT.graph_validator.validate(group)
    return EditResponse(
        blob=edited,
        valid=not issues,
        issues=issues,
        explored=PipelineExplorer.explore(group),
    )


@router.post("/ingest/stages/view", response_model=StageViewResponse)
@auto_handle_errors
async def view_ingest_stages(request: StageViewRequest) -> StageViewResponse:
    """
    Derive the stage view of a blob — the full ordered skeleton, greyed where off — plus its
    validity, folded in so the product UI opens on this ONE call (no priming /inspect).

    Returns:
        StageViewResponse: The canonical stages (toggles, providers, chains, stack) read from
        the blob by family, with the blob's validity verdict (an unbuildable blob is DATA:
        valid=false + build_error, never an HTTP error).
    """
    # 1. Read the blob into the canonical state and view it as the ordered stage list.
    stages = StageViewer.catalog(StateReader.read(request.blob)).stages

    # 2. Build + validate — a blob that cannot even be built is surfaced, not raised.
    try:
        group = CONTEXT.pipeline_builder.build(request.blob)
    except BuildError as exc:
        return StageViewResponse(stages=stages, valid=False, build_error=str(exc))
    issues = CONTEXT.graph_validator.validate(group)
    return StageViewResponse(stages=stages, valid=not issues, issues=issues)


@router.post("/ingest/stages/apply", response_model=StageApplyResponse)
@auto_handle_errors
async def apply_ingest_stage_action(request: StageApplyRequest) -> StageApplyResponse:
    """
    Compile a stage-level action into a blob transformation, then view + validate the result.

    The compiler ALWAYS returns a buildable, correctly wired blob (dependency cascades and
    rebindings are handled server-side); validation issues are only the required configs the user
    must still fill — expected and shown, never a 500.

    Returns:
        StageApplyResponse: The recompiled blob, its stage view, validity, issues and notices.
    """
    # 1. Compile the action — the assembler rewires every consumer to its nearest enabled producer.
    blob, notices = CONTEXT.stage_compiler.apply(request.blob, request.action)

    # 2. Build + validate the recompiled blob — an unbuildable result is DATA the user
    #    fixes in place (missing required config), never an HTTP error.
    stages = StageViewer.catalog(StateReader.read(blob)).stages
    try:
        group = CONTEXT.pipeline_builder.build(blob)
    except BuildError as exc:
        return StageApplyResponse(
            blob=blob, stages=stages, valid=False, issues=[], notices=notices,
            build_error=str(exc),
        )
    issues = CONTEXT.graph_validator.validate(group)

    # 3. View the recompiled blob so the UI re-renders from the backend's truth.
    return StageApplyResponse(
        blob=blob, stages=stages, valid=not issues, issues=issues, notices=notices
    )


__all__ = ["router"]
