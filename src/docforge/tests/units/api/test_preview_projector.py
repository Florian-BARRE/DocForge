"""PreviewProjector — the PURE projection of an inline dry-run's in-memory result into the bounded
report. It proves the feature's heart WITHOUT a store: a delivered RunBundle yields an IR summary +
the first N chunks (text clipped, the rest only counted) + the ACTUAL metered cost + the flattened
execution trace; a zero-chunk delivery is a warning (not a failure); and a failed run (no bundle) is
DATA — ok=false + the deepest failing node + its partial trace — never an exception.
"""

import pathlib
import sys

# The ``backend`` package lives under app/ — put it on the path exactly as the api conftest's
# fastapi_app fixture does, so this pure test module imports it at collection time without booting.
_APP_DIR = str(pathlib.Path(__file__).resolve().parents[3] / "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from shared_libs.pipelines.base import (  # noqa: E402
    ErrorInfo,
    NodeExecutionRecord,
    NodeStatus,
    NodeUsage,
)
from shared_libs.pipelines.ingest.estimate import RateTable  # noqa: E402
from shared_libs.pipelines.preview.projector import PreviewProjector  # noqa: E402
from shared_libs.public_models import (  # noqa: E402
    Chunk,
    DocumentIR,
    IntakeResult,
    Provenance,
    RunBundle,
)
from shared_libs.public_models.ir import Block, BlockType  # noqa: E402


def _block(block_id: str, block_type: BlockType, order: int) -> Block:
    return Block(
        id=block_id,
        block_type=block_type,
        provenance=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 1.0)),
        reading_order=order,
        text="x",
    )


def _ir() -> DocumentIR:
    """A tiny IR: one heading, one paragraph, one figure — enough to exercise the type counts."""
    return DocumentIR(
        doc_id="doc-1",
        source_hash="hash-1",
        title="Title",
        n_pages=2,
        language="en",
        blocks=[
            _block("b0", BlockType.HEADING, 0),
            _block("b1", BlockType.PARAGRAPH, 1),
            _block("b2", BlockType.FIGURE, 2),
        ],
    )


def _chunk(ordinal: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"c{ordinal}",
        ordinal=ordinal,
        text=text,
        token_count=len(text.split()),
        page_start=0,
        page_end=0,
    )


def _bundle(n_chunks: int) -> RunBundle:
    return RunBundle(
        ingest=IntakeResult(source_hash="hash-1", source_format="pdf", page_count=2),
        ir=_ir(),
        chunks=[_chunk(i, f"chunk text {i}") for i in range(n_chunks)],
    )


def _record_with_cost() -> NodeExecutionRecord:
    """A 2-node tree: a group wrapping one paid LLM leaf (so UsageSummer has something to price)."""
    leaf = NodeExecutionRecord(
        node_id="metagen_chunk",
        kind="llm",
        status=NodeStatus.SUCCESS,
        duration_ms=12.0,
        usage=NodeUsage(model="gpt-4o-mini", prompt_tokens=1000, completion_tokens=200),
    )
    return NodeExecutionRecord(
        node_id="__root__",
        kind="group",
        status=NodeStatus.SUCCESS,
        duration_ms=30.0,
        children=[leaf],
    )


def test_delivered_run_projects_chunks_cost_and_trace() -> None:
    """A delivered bundle → ok, IR summary, the first N chunks (text clipped), priced cost, a trace."""
    # 1. Three chunks, a max of two returned, a tight 6-char text clip.
    response = PreviewProjector.project(
        _bundle(3),
        _record_with_cost(),
        RateTable.default(),
        source_filename="doc.pdf",
        max_chunks=2,
        text_max_chars=6,
    )

    # 2. Delivered → ok, IR summary populated, the chunk count is the FULL total.
    assert response.ok is True
    assert response.ir is not None
    assert response.ir.page_count == 2
    assert response.ir.figure_count == 1
    assert response.ir.block_type_counts.get(str(BlockType.HEADING)) == 1
    assert response.chunk_count == 3

    # 3. Only N chunks come back, flagged truncated, and their text is clipped to the ceiling.
    assert len(response.chunks) == 2
    assert response.chunks_truncated is True
    assert response.chunks[0].text == "chunk "
    assert response.chunks[0].text_truncated is True

    # 4. The ACTUAL spend is metered from the record (priced model → a real, non-null cost).
    assert response.cost.prompt_tokens == 1000
    assert response.cost.completion_tokens == 200
    assert response.cost.cost_usd is not None and response.cost.cost_usd > 0
    assert response.cost.priced_call_count == 1

    # 5. The full execution tree is flattened (the group's child leaf), roots first.
    assert [node.node_id for node in response.trace] == ["metagen_chunk"]
    assert response.trace[0].depth == 0
    assert response.warnings == []


def test_zero_chunk_delivery_is_a_warning_not_a_failure() -> None:
    """A clean run that produced 0 chunks is ok=true WITH a visible warning — never marked failed."""
    response = PreviewProjector.project(
        _bundle(0),
        _record_with_cost(),
        RateTable.default(),
        source_filename="empty.pdf",
        max_chunks=5,
        text_max_chars=100,
    )
    assert response.ok is True
    assert response.chunk_count == 0
    assert response.chunks == []
    assert any("0 chunks" in warning for warning in response.warnings)


def test_failed_run_is_data_not_an_exception() -> None:
    """No delivery (a node raised) → ok=false + the deepest failing node + its partial trace."""
    # 1. A group wrapping a FAILED leaf with a captured error (the engine's failed-run shape).
    failed_leaf = NodeExecutionRecord(
        node_id="parse_docling",
        kind="docling",
        status=NodeStatus.FAILED,
        duration_ms=5.0,
        error=ErrorInfo(error_type="RuntimeError", message="parser blew up"),
    )
    root = NodeExecutionRecord(
        node_id="__root__",
        kind="group",
        status=NodeStatus.FAILED,
        duration_ms=6.0,
        children=[failed_leaf],
    )

    response = PreviewProjector.project(
        None,
        root,
        RateTable.default(),
        source_filename="bad.pdf",
        max_chunks=5,
        text_max_chars=100,
    )

    # 2. Reported as DATA, not raised: ok=false, no IR, the failing node named, the trace present.
    assert response.ok is False
    assert response.ir is None
    assert response.chunk_count == 0
    assert response.failed_node_id == "parse_docling"
    assert response.failed_node_kind == "docling"
    assert "RuntimeError" in (response.error or "")
    assert response.trace[0].status == str(NodeStatus.FAILED)
