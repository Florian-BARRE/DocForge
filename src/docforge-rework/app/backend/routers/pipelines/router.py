# ====== Code Summary ======
# Route definitions for the pipeline design surface — parameterized over the PipelineRegistry so the
# SAME endpoints serve every pipeline kind (ingest, search) with zero per-pipeline code. The product
# path: the lean design GET (palette families + blob) and the stage endpoints (/stages/view with
# folded validity, /stages/apply). Advanced, headless path: ?full=true (full palette), /inspect and
# /edit (described tree + graph operations). The UI carries zero hardcoded pipeline knowledge —
# discovery (`GET /pipelines`) lists every surface and everything it renders comes from these
# endpoints. Stage endpoints are ingest-only today (search has no stage rail yet): an unsupported
# key 404s, and the discovery index omits the stage URLs for those pipelines.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError
from shared_libs.pipelines.edit import EditError
from shared_libs.pipelines.ingest.stages import StageViewer, StateReader
from shared_libs.pipelines.introspection import PipelineExplorer
from shared_libs.pipelines.pipeline_registry import PipelineRegistry, PipelineSpec

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


def _resolve_spec(key: str) -> PipelineSpec:
    """
    Resolve a pipeline spec by URL key or raise a 404 — the guard every keyed route shares.

    Args:
        key (str): The pipeline key from the path (e.g. ``"ingest"``, ``"search"``).

    Returns:
        PipelineSpec: The matching registry spec.

    Raises:
        HTTPException: 404 when the key names no registered pipeline.
    """
    # 1. An unknown pipeline kind is a genuine not-found (unlike a broken blob, which is data).
    spec = PipelineRegistry.get(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline '{key}'.")
    return spec


def _require_stage_surface(key: str) -> PipelineSpec:
    """
    Resolve a pipeline spec that MUST expose a stage rail, or raise a 404.

    Args:
        key (str): The pipeline key from the path.

    Returns:
        PipelineSpec: The matching spec, guaranteed ``supports_stages``.

    Raises:
        HTTPException: 404 when the key is unknown OR the pipeline has no stage rail (the stage
            layer is ingest-coupled; search is advanced/headless-only for now).
    """
    # 1. Resolve, then reject a pipeline with no stage surface (honest 404, no meaningless view).
    spec = _resolve_spec(key)
    if not spec.supports_stages:
        raise HTTPException(status_code=404, detail=f"Pipeline '{key}' has no stage surface.")
    return spec


@router.get("", response_model=PipelineIndexResponse)
@auto_handle_errors
async def list_pipeline_surfaces() -> PipelineIndexResponse:
    """
    Discover the available pipeline design surfaces — the UI's single bootstrap call.

    Returns:
        PipelineIndexResponse: One entry per registered pipeline, each with its design/inspect URLs
        (stage URLs only for pipelines that expose a stage rail).
    """
    # 1. One entry per registered pipeline — the URLs are derived from the key, so a new pipeline
    #    kind needs zero router change (only a PipelineRegistry entry).
    surfaces = [
        PipelineSurface(
            key=spec.key,
            title=spec.title,
            description=spec.description,
            design_url=f"/api/v1/pipelines/{spec.key}",
            inspect_url=f"/api/v1/pipelines/{spec.key}/inspect",
            edit_url=f"/api/v1/pipelines/{spec.key}/edit",
            stages_view_url=(
                f"/api/v1/pipelines/{spec.key}/stages/view" if spec.supports_stages else None
            ),
            stages_apply_url=(
                f"/api/v1/pipelines/{spec.key}/stages/apply" if spec.supports_stages else None
            ),
        )
        for spec in PipelineRegistry.specs()
    ]
    return PipelineIndexResponse(pipelines=surfaces)


@router.get("/{key}", response_model=PipelineDesignResponse)
@auto_handle_errors
async def get_pipeline_design(key: str, full: bool = False) -> PipelineDesignResponse:
    """
    Open a pipeline design surface: palette + default blob + its issues.

    The default payload is lean — exactly what the product stage rail consumes (families +
    blob). ``?full=true`` upgrades the SAME payload with the advanced palette blocks
    (run_inputs, mechanics, artefacts) for headless graph-level tooling; the described tree
    of a blob is served by ``/inspect`` and ``/edit``.

    Args:
        key (str): The pipeline key (``ingest`` / ``search``).
        full (bool): Query flag — when true, fill the advanced palette blocks.

    Returns:
        PipelineDesignResponse: The blocks catalogue, the editable blob and any validation
        issues (empty for the stock pipeline). 404 when the pipeline key is unknown.
    """
    # 1. Resolve the pipeline facade behind the key (404 on an unknown pipeline kind).
    facade = _resolve_spec(key).facade

    # 2. The editable truth — the pipeline's default topology (per-collection blobs come later).
    blob = facade.default_blob()

    # 3. Build transiently, only to validate — instances die with the request.
    group = CONTEXT.pipeline_builder.build(blob)
    issues = CONTEXT.graph_validator.validate(group)

    # 4. One payload; the product UI needs nothing else to construct itself.
    return PipelineDesignResponse(
        palette=facade.palette(full=full),
        blob=blob,
        issues=issues,
    )


@router.post("/{key}/inspect", response_model=InspectResponse)
@auto_handle_errors
async def inspect_pipeline(key: str, request: InspectRequest) -> InspectResponse:
    """
    Build + validate + describe an edited pipeline blob — the editor's feedback loop.

    The inspect logic is pipeline-agnostic (it operates on the posted blob); ``key`` only scopes
    the surface and 404s when unknown.

    Returns:
        InspectResponse: valid flag, every validation issue, and the described tree.
    """
    # 1. Scope to a known pipeline (404 otherwise).
    _resolve_spec(key)

    # 2. Rebuild the live graph; a malformed blob is editor DATA, not an HTTP error.
    try:
        group = CONTEXT.pipeline_builder.build(request.blob)
    except BuildError as exc:
        return InspectResponse(valid=False, build_error=str(exc))

    # 3. Collect ALL validation issues (the validator never stops at the first one).
    issues = CONTEXT.graph_validator.validate(group)

    # 4. Describe the built tree so the UI re-renders from the backend's truth.
    return InspectResponse(
        valid=not issues,
        issues=issues,
        explored=PipelineExplorer.explore(group),
    )


@router.post("/{key}/edit", response_model=EditResponse)
@auto_handle_errors
async def edit_pipeline(key: str, request: EditRequest) -> EditResponse:
    """
    Apply graph operations to a blob server-side, then build + validate + describe the result.

    The editing/healing semantics live here, next to the invariants, so no client re-implements
    them. An impossible operation is DATA (edit_error set, original blob echoed, valid=false),
    never a 500; a merely invalid result comes back with its issues, exactly like /inspect. The
    logic is pipeline-agnostic; ``key`` only scopes the surface and 404s when unknown.

    Returns:
        EditResponse: the edited blob, its validity, every issue, the described tree, edit_error.
    """
    # 1. Scope to a known pipeline (404 otherwise).
    _resolve_spec(key)

    # 2. Apply the operations to a deep copy; an impossible op is editor DATA, not an HTTP error.
    try:
        edited = CONTEXT.graph_editor.apply(request.blob, request.operations)
    except EditError as exc:
        return EditResponse(blob=request.blob, valid=False, edit_error=str(exc))

    # 3. Rebuild the edited blob; an unbuildable RESULT (a bad config) is surfaced, not raised.
    try:
        group = CONTEXT.pipeline_builder.build(edited)
    except BuildError as exc:
        return EditResponse(blob=edited, valid=False, edit_error=str(exc))

    # 4. Collect ALL validation issues and describe the tree — same feedback loop as /inspect.
    issues = CONTEXT.graph_validator.validate(group)
    return EditResponse(
        blob=edited,
        valid=not issues,
        issues=issues,
        explored=PipelineExplorer.explore(group),
    )


@router.post("/{key}/stages/view", response_model=StageViewResponse)
@auto_handle_errors
async def view_stages(key: str, request: StageViewRequest) -> StageViewResponse:
    """
    Derive the stage view of a blob — the full ordered skeleton, greyed where off — plus its
    validity, folded in so the product UI opens on this ONE call (no priming /inspect).

    The stage layer is ingest-coupled today, so an unknown OR non-stage pipeline key 404s.

    Returns:
        StageViewResponse: The canonical stages (toggles, providers, chains, stack) read from
        the blob by family, with the blob's validity verdict (an unbuildable blob is DATA:
        valid=false + build_error, never an HTTP error).
    """
    # 1. Only a stage-bearing pipeline reaches the stage machinery (404 otherwise).
    _require_stage_surface(key)

    # 2. Read the blob into the canonical state and view it as the ordered stage list.
    stages = StageViewer.catalog(StateReader.read(request.blob)).stages

    # 3. Build + validate — a blob that cannot even be built is surfaced, not raised.
    try:
        group = CONTEXT.pipeline_builder.build(request.blob)
    except BuildError as exc:
        return StageViewResponse(stages=stages, valid=False, build_error=str(exc))
    issues = CONTEXT.graph_validator.validate(group)
    return StageViewResponse(stages=stages, valid=not issues, issues=issues)


@router.post("/{key}/stages/apply", response_model=StageApplyResponse)
@auto_handle_errors
async def apply_stage_action(key: str, request: StageApplyRequest) -> StageApplyResponse:
    """
    Compile a stage-level action into a blob transformation, then view + validate the result.

    The compiler ALWAYS returns a buildable, correctly wired blob (dependency cascades and
    rebindings are handled server-side); validation issues are only the required configs the user
    must still fill — expected and shown, never a 500. Ingest-only today: an unknown OR non-stage
    pipeline key 404s.

    Returns:
        StageApplyResponse: The recompiled blob, its stage view, validity, issues and notices.
    """
    # 1. Only a stage-bearing pipeline reaches the stage compiler (404 otherwise).
    _require_stage_surface(key)

    # 2. Compile the action — the assembler rewires every consumer to its nearest enabled producer.
    blob, notices = CONTEXT.stage_compiler.apply(request.blob, request.action)

    # 3. Build + validate the recompiled blob — an unbuildable result is DATA the user
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

    # 4. View the recompiled blob so the UI re-renders from the backend's truth.
    return StageApplyResponse(
        blob=blob, stages=stages, valid=not issues, issues=issues, notices=notices
    )


__all__ = ["router"]
