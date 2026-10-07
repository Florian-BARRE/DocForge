"""Replay-from-stage — the engine's mid-graph start (ResumePoint) on the REAL default ingest graph,
the pure ReplayPlanner (supported vs refused stages + the fidelity of each seed) and the
ReplaySeeder."""

import uuid
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.base import NodeStatus
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.replay import (
    REPLAYABLE_STAGES,
    PersistedArtifacts,
    ReplayPlanner,
    ReplaySeeder,
    ReplayUnsupportedError,
    SeedKind,
)
from shared_libs.pipelines.ingest.stages import EnableStage, StageCompiler, StageKey
from shared_libs.public_models import (
    Block,
    BlockType,
    Chunk,
    ChunkEmbeddings,
    CollectionContract,
    DocumentIR,
    FigureEnrichment,
    FigureKind,
    IntakeResult,
    Provenance,
    RunBundle,
    SourceDocument,
)


def _ir() -> DocumentIR:
    """A small IR: a heading, two paragraphs, and an enriched figure."""

    def block(i: int, kind: BlockType, text: str | None, **extra) -> Block:
        return Block(
            id=f"b{i}",
            block_type=kind,
            provenance=Provenance(page=0, bbox=(0.0, 0.1 * i, 1.0, 0.1 * i + 0.05)),
            reading_order=i,
            text=text,
            **extra,
        )

    return DocumentIR(
        doc_id="d",
        source_hash="h",
        n_pages=1,
        language="en",
        blocks=[
            block(0, BlockType.HEADING, "Introduction", level=1),
            block(
                1, BlockType.PARAGRAPH, "Replay re-runs only the downstream stages.", parent_id="b0"
            ),
            block(2, BlockType.PARAGRAPH, "The parse stage never runs again.", parent_id="b0"),
            block(
                3,
                BlockType.FIGURE,
                None,
                figure=FigureEnrichment(kind=FigureKind.CHART, description="A bar chart of costs."),
            ),
        ],
    )


def _full_blob():
    blob = IngestPipeline.default_blob()
    for stage in ("enrich", "metagen_chunk", "metagen_document"):
        blob, _ = StageCompiler().apply(blob, EnableStage(stage=stage))
    return blob


def _run_input() -> dict:
    contract = CollectionContract(
        collection_id=uuid.uuid4(), name="c", supported_formats=["md"], max_file_size_bytes=10
    )
    return {"source": SourceDocument(filename="a.md", content=b"x"), "contract": contract}


# ---------------------------------------------------------------- planner


def test_default_pipeline_allows_only_post_ir_stages_it_runs() -> None:
    group = PipelineBuilder().build(IngestPipeline.default_blob())
    assert ReplayPlanner.allowed(group) == ["chunk", "embed"]


def test_full_pipeline_allows_every_persisted_stage_but_contextualize() -> None:
    group = PipelineBuilder().build(_full_blob())
    assert ReplayPlanner.allowed(group) == [
        "enrich",
        "chunk",
        "metagen_chunk",
        "metagen_document",
        "embed",
    ]


@pytest.mark.parametrize("stage", ["parse", "intake", "render", "language", "nope"])
def test_pre_ir_or_unknown_stage_is_refused(stage: str) -> None:
    group = PipelineBuilder().build(_full_blob())
    with pytest.raises(ReplayUnsupportedError, match="not a replayable stage"):
        ReplayPlanner.plan(group, stage)


def test_contextualize_is_refused_because_raw_chunk_text_is_not_persisted() -> None:
    """L-2: contextualize is never replayable on a shipped pipeline, so it is not in the allowed list
    and its refusal points at 'chunk' — the 422 `allowed` list and the reason stay consistent."""
    group = PipelineBuilder().build(_full_blob())
    with pytest.raises(ReplayUnsupportedError, match="replay from 'chunk' instead"):
        ReplayPlanner.plan(group, "contextualize")
    assert "contextualize" not in ReplayPlanner.allowed(group)
    assert StageKey.CONTEXTUALIZE not in REPLAYABLE_STAGES


def test_disabled_stage_is_refused() -> None:
    group = PipelineBuilder().build(IngestPipeline.default_blob())
    with pytest.raises(ReplayUnsupportedError, match="not enabled"):
        ReplayPlanner.plan(group, "metagen_document")


def test_embed_plan_seeds_final_chunks_with_meta_and_never_reaches_parse() -> None:
    plan = ReplayPlanner.plan(PipelineBuilder().build(_full_blob()), "embed")
    assert plan.start_node_id == "embed"
    assert plan.downstream_ids == {"embed", "bundle"}
    chunks = next(need for need in plan.needs if need.kind is SeedKind.CHUNKS)
    assert chunks.node_id == "meta_chunk_apply" and chunks.with_generated_meta


def test_enrich_plan_strips_enrichments_and_needs_crops() -> None:
    plan = ReplayPlanner.plan(PipelineBuilder().build(_full_blob()), "enrich")
    ir_need = next(
        need for need in plan.needs if need.node_id == "figures" and need.kind is SeedKind.IR
    )
    assert not ir_need.with_enrichments and plan.needs_crops


def test_seeder_strips_enrichments_and_generated_meta_at_the_producer() -> None:
    group = PipelineBuilder().build(_full_blob())
    plan = ReplayPlanner.plan(group, "enrich")
    persisted = PersistedArtifacts(ingest=IntakeResult(source_hash="h"), ir=_ir())
    resume = ReplaySeeder.resume_point(plan, group, persisted)
    figure = resume.seeded_outputs["figures"].ir.blocks[3].figure
    assert figure.description is None and figure.kind is FigureKind.PHOTO
    # The persisted artefact itself is never mutated (the run gets copies).
    assert persisted.ir.blocks[3].figure.description == "A bar chart of costs."

    plan = ReplayPlanner.plan(group, "metagen_chunk")
    persisted.chunks = [Chunk(chunk_id="c0", ordinal=0, text="t", generated_meta={"k": "v"})]
    resume = ReplaySeeder.resume_point(plan, group, persisted)
    assert resume.seeded_outputs["ctx_breadcrumb"].chunks[0].generated_meta == {}


# ---------------------------------------------------------------- engine mid-graph start


def _patch_embed(group) -> None:
    embed = next(child for child in group.children if child.id == "embed")

    async def fake_run(data):
        return embed.Produces(embeddings=ChunkEmbeddings(model="m", dimension=0, items=[]))

    embed.run = fake_run


async def test_resume_from_chunk_runs_only_downstream_and_never_parses() -> None:
    group = PipelineBuilder().build(IngestPipeline.default_blob())
    for child in group.children:
        if child.id not in {"chunk", "ctx_meta", "ctx_breadcrumb", "embed", "bundle"}:
            child.run = AsyncMock(side_effect=AssertionError(f"{child.id} must not run"))
    _patch_embed(group)
    plan = ReplayPlanner.plan(group, "chunk")
    persisted = PersistedArtifacts(ingest=IntakeResult(source_hash="h"), ir=_ir())
    resume = ReplaySeeder.resume_point(plan, group, persisted)

    output, record = await FlowEngine().execute(group, _run_input(), resume=resume)

    assert record.status == NodeStatus.SUCCESS
    ran = [child.node_id for child in record.children]
    assert ran == ["chunk", "ctx_meta", "ctx_breadcrumb", "embed", "bundle"]
    assert "parse" not in ran
    bundle = output.bundle
    assert isinstance(bundle, RunBundle) and bundle.chunks
    # Enrich is OFF in the default pipeline: the IR seeded at the render producer drops the stored
    # figure enrichment (the chunks match what a full run of THIS pipeline would build).
    assert "bar chart" not in " ".join(chunk.text for chunk in bundle.chunks)


async def test_unknown_start_node_is_a_recorded_failure_not_a_crash() -> None:
    from shared_libs.pipelines.engine import ResumePoint

    group = PipelineBuilder().build(IngestPipeline.default_blob())
    output, record = await FlowEngine().execute(
        group, _run_input(), resume=ResumePoint(start_node_id="ghost")
    )
    assert output is None and record.status == NodeStatus.FAILED


# ---------------------------------------------------------------- replay fidelity (L-6)


def _ir_with_table_and_figure(enriched: bool) -> DocumentIR:
    """The parse-time IR (figure placeholder) or the persisted one (figure enriched later on)."""
    from shared_libs.public_models import TableData  # noqa: PLC0415

    ir = _ir()
    ir.blocks.append(
        Block(
            id="b4",
            block_type=BlockType.TABLE,
            provenance=Provenance(page=0, bbox=(0.0, 0.5, 1.0, 0.6)),
            reading_order=4,
            parent_id="b0",
            table=TableData(
                cells=[["stage", "cost"], ["parse", "0"], ["embed", "1"]],
                n_rows=3,
                n_cols=2,
                has_header=True,
            ),
        )
    )
    if not enriched:
        ir.blocks[3].figure = FigureEnrichment()
    return ir


def _chunk_view(bundle: RunBundle) -> list[tuple]:
    return [
        (c.ordinal, c.text, c.enriched_text, c.role, tuple(c.block_ids), tuple(c.heading_path))
        for c in bundle.chunks
    ]


async def test_replay_at_chunk_yields_the_same_chunks_as_a_full_run_on_the_same_ir() -> None:
    """L-6: chunks rebuilt by a replay at 'chunk' (persisted IR — figure ENRICHED since, stripped by
    the seeder because enrich is off) equal a full run's chunks over the parse-time IR, table and
    figure included."""
    from shared_libs.pipelines.base import NodeInput  # noqa: PLC0415
    from shared_libs.public_models import PageRenders  # noqa: PLC0415

    class _NoInput(NodeInput):
        pass

    upstream = {"probe", "admit", "convert", "pdf_probe", "address", "parse", "language", "figures"}

    # 1. Full run: every pre-chunk node is stubbed (no I/O), the render step hands chunk the IR.
    full = PipelineBuilder().build(IngestPipeline.default_blob())
    for child in full.children:
        if child.id in upstream:
            child.Consumes = _NoInput
            fields = {}
            if child.id == "address":
                fields = {"ingest": IntakeResult(source_hash="h")}
            if child.id == "figures":
                fields = {"ir": _ir_with_table_and_figure(enriched=False), "pages": PageRenders()}
            child.run = AsyncMock(return_value=child.Produces.model_construct(**fields))
    _patch_embed(full)
    full_out, full_record = await FlowEngine().execute(full, _run_input())
    assert full_record.status == NodeStatus.SUCCESS

    # 2. Replay from chunk on the persisted state.
    group = PipelineBuilder().build(IngestPipeline.default_blob())
    _patch_embed(group)
    plan = ReplayPlanner.plan(group, "chunk")
    persisted = PersistedArtifacts(
        ingest=IntakeResult(source_hash="h"), ir=_ir_with_table_and_figure(enriched=True)
    )
    replay_out, replay_record = await FlowEngine().execute(
        group, _run_input(), resume=ReplaySeeder.resume_point(plan, group, persisted)
    )
    assert replay_record.status == NodeStatus.SUCCESS

    # 3. Same chunks, the table rendered in both.
    full_chunks, replay_chunks = _chunk_view(full_out.bundle), _chunk_view(replay_out.bundle)
    assert full_chunks and full_chunks == replay_chunks
    assert any("embed" in text for _, text, *_ in replay_chunks)
