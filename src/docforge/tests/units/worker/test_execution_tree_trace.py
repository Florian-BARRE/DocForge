"""JobApi.persist_execution_tree — the trace columns it writes per node: the cheap shape summary
rides inline on the record for every captured node, while the full-payload refs + has_full_* flags
come from the worker's pre-stored object-store keys (``refs``), keyed by materialized path. A node
absent from ``refs`` keeps has_full false / refs None even though it has a shape summary. Postgres is
a minimal fake session (no real DB) — this only exercises the INSERT branch (no pre-existing rows),
which is enough to pin what gets written onto a fresh JobStageEvent.
"""

import uuid
from unittest.mock import MagicMock

from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus
from shared_libs.services.db.postgresql.apis.execution_tree import TraceRefs
from shared_libs.services.db.postgresql.apis.job_api import JobApi


def _rec(
    node_id: str,
    *,
    input_summary: dict | None = None,
    output_summary: dict | None = None,
    children: list[NodeExecutionRecord] | None = None,
) -> NodeExecutionRecord:
    return NodeExecutionRecord(
        node_id=node_id,
        kind="action",
        status=NodeStatus.SUCCESS,
        duration_ms=1.0,
        input_summary=input_summary,
        output_summary=output_summary,
        children=children or [],
    )


class _FakeSession:
    """No pre-existing rows: every flattened node takes the INSERT branch via ``session.add``."""

    def __init__(self) -> None:
        self.added: list = []
        self.flushed = False

    async def execute(self, _statement):
        result = MagicMock()
        result.all.return_value = []
        return result

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed = True


async def test_shape_only_node_gets_inline_summary_and_no_full_refs() -> None:
    """A SHAPE-tier node writes its input/output summary inline; refs/has_full stay unset."""
    shape_leaf = _rec(
        "shape_leaf", input_summary={"type": "Doc"}, output_summary={"type": "DocOut"}
    )
    root = _rec("pipeline", children=[shape_leaf])
    session = _FakeSession()

    await JobApi.persist_execution_tree(session, uuid.uuid4(), root, refs=None)

    row = next(r for r in session.added if r.node_path == "shape_leaf")
    assert row.input_summary == {"type": "Doc"}
    assert row.output_summary == {"type": "DocOut"}
    assert row.input_ref is None
    assert row.output_ref is None
    assert row.has_full_input is False
    assert row.has_full_output is False
    assert session.flushed is True


async def test_full_node_gets_refs_and_has_full_flags_set() -> None:
    """A FULL-tier node (present in ``refs``) writes its object-store keys + has_full=True, on top
    of the same inline shape summary a shape-only node gets."""
    full_leaf = _rec("full_leaf", input_summary={"type": "Doc"}, output_summary={"type": "DocOut"})
    root = _rec("pipeline", children=[full_leaf])
    refs = {"full_leaf": TraceRefs(input_ref="s3://in-key", output_ref="s3://out-key")}
    session = _FakeSession()

    await JobApi.persist_execution_tree(session, uuid.uuid4(), root, refs=refs)

    row = next(r for r in session.added if r.node_path == "full_leaf")
    assert row.input_summary == {"type": "Doc"}
    assert row.output_summary == {"type": "DocOut"}
    assert row.input_ref == "s3://in-key"
    assert row.output_ref == "s3://out-key"
    assert row.has_full_input is True
    assert row.has_full_output is True


async def test_a_node_absent_from_refs_has_full_false_even_with_other_full_nodes_present() -> None:
    """Mixed tree: only the node actually present in ``refs`` gets has_full=True; its sibling — a
    shape-only capture in the SAME run — is untouched by another node's refs entry."""
    shape_leaf = _rec("shape_leaf", input_summary={"type": "Doc"})
    full_leaf = _rec("full_leaf", input_summary={"type": "Doc"})
    root = _rec("pipeline", children=[shape_leaf, full_leaf])
    refs = {"full_leaf": TraceRefs(input_ref="s3://in-key")}
    session = _FakeSession()

    await JobApi.persist_execution_tree(session, uuid.uuid4(), root, refs=refs)

    shape_row = next(r for r in session.added if r.node_path == "shape_leaf")
    full_row = next(r for r in session.added if r.node_path == "full_leaf")
    assert shape_row.has_full_input is False and shape_row.input_ref is None
    assert full_row.has_full_input is True and full_row.input_ref == "s3://in-key"
    # Only the input side was stored — the output side stays unset even for the full-tier node.
    assert full_row.has_full_output is False and full_row.output_ref is None
