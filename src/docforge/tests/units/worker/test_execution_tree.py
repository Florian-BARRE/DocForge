"""ExecutionTreeFlattener + JobApi._trace_sort_key — the materialized-path model that persists the
FULL per-node execution tree (nested group children and per-item ForEach body instances) and reads
it back parent-before-child with ForEach items in ascending index order."""

from types import SimpleNamespace

from shared_libs.pipelines.base import NodeExecutionRecord, NodeStatus
from shared_libs.services.db.postgresql.apis import ExecutionTreeFlattener
from shared_libs.services.db.postgresql.apis.job_api import JobApi


def _rec(
    node_id: str,
    *,
    kind: str = "action",
    score: float | None = None,
    children: list[NodeExecutionRecord] | None = None,
) -> NodeExecutionRecord:
    """A minimal execution record for the flattener (status/duration are irrelevant to the walk)."""
    return NodeExecutionRecord(
        node_id=node_id,
        kind=kind,
        status=NodeStatus.SUCCESS,
        duration_ms=1.0,
        score=score,
        children=children or [],
    )


def _tree() -> NodeExecutionRecord:
    """Outermost group with a scored root stage and a ForEach fan-out of two items."""
    body0 = _rec("figbody[0]", kind="group", children=[_rec("vlm", kind="vlm")])
    body1 = _rec("figbody[1]", kind="group", children=[_rec("vlm", kind="vlm")])
    figures = _rec("figures", kind="foreach", children=[body0, body1])
    enrich = _rec("enrich", kind="group", children=[figures])
    parse = _rec("parse", kind="parser", score=0.91)
    return _rec("pipeline", kind="group", children=[parse, enrich])


def test_flatten_computes_paths_depths_and_item_indices() -> None:
    """Every node is emitted with its materialized path, depth and inherited fan-out item index."""
    flat = {node.node_path: node for node in ExecutionTreeFlattener.flatten(_tree())}

    # 1. Depth-0 roots keep their bare id and carry no parent.
    assert flat["parse"].depth == 0 and flat["parse"].parent_path is None
    assert flat["parse"].record.score == 0.91
    assert flat["enrich"].depth == 0

    # 2. Nesting appends the child's id to the parent path and bumps the depth.
    assert flat["enrich.figures"].depth == 1
    assert flat["enrich.figures"].parent_path == "enrich"

    # 3. A ForEach body item derives its index from the ``[n]`` suffix; a descendant inherits it.
    item0 = flat["enrich.figures.figbody[0]"]
    assert (item0.depth, item0.item_index) == (2, 0)
    vlm0 = flat["enrich.figures.figbody[0].vlm"]
    assert (vlm0.depth, vlm0.item_index, vlm0.parent_path) == (
        3,
        0,
        "enrich.figures.figbody[0]",
    )
    assert flat["enrich.figures.figbody[1].vlm"].item_index == 1


def test_flatten_is_parent_before_child_order() -> None:
    """The flat list is a pre-order walk: a parent always precedes each of its descendants."""
    paths = [node.node_path for node in ExecutionTreeFlattener.flatten(_tree())]
    assert paths.index("enrich") < paths.index("enrich.figures")
    assert paths.index("enrich.figures") < paths.index("enrich.figures.figbody[0]")


def test_trace_sort_key_orders_tree_and_foreach_indices_numerically() -> None:
    """The read sort key gives a stable pre-order walk with ForEach items in numeric index order."""
    scrambled = [
        SimpleNamespace(node_path="enrich.figures.figbody[10].vlm", created_at=0),
        SimpleNamespace(node_path="enrich.figures.figbody[2].vlm", created_at=0),
        SimpleNamespace(node_path="enrich", created_at=0),
        SimpleNamespace(node_path="enrich.figures", created_at=0),
    ]
    ordered = [e.node_path for e in sorted(scrambled, key=JobApi._trace_sort_key)]
    assert ordered == [
        "enrich",
        "enrich.figures",
        "enrich.figures.figbody[2].vlm",
        "enrich.figures.figbody[10].vlm",
    ]


def test_trace_sort_key_puts_legacy_rows_first_in_insertion_order() -> None:
    """Legacy rows (node_path NULL) sort ahead of path rows, ordered by created_at."""
    import datetime

    older = SimpleNamespace(node_path=None, created_at=datetime.datetime(2026, 1, 1))
    newer = SimpleNamespace(node_path=None, created_at=datetime.datetime(2026, 1, 2))
    path_row = SimpleNamespace(node_path="parse", created_at=datetime.datetime(2026, 1, 3))
    ordered = sorted([newer, path_row, older], key=JobApi._trace_sort_key)
    assert ordered == [older, newer, path_row]
