"""UNIQUE_IN_GRAPH doctrine: a singleton kind duplicated anywhere in the graph is rejected;
repeatable kinds (e.g. llm_context) may appear more than once. Ported from the scratchpad's
test_contextualize_stage.py (section 6).
"""

from shared_libs.pipelines.ingest.nodes.contextualize.breadcrumb import ContextualizerBreadcrumbNode
from shared_libs.pipelines.ingest.nodes.contextualize.llm import ContextualizerLlmNode


def test_breadcrumb_is_flagged_unique_in_graph() -> None:
    assert ContextualizerBreadcrumbNode.describe().unique_in_graph is True


def test_llm_context_is_not_unique_in_graph() -> None:
    """Two situating passes (e.g. different scopes) is a legitimate stack."""
    assert ContextualizerLlmNode.describe().unique_in_graph is False


def test_duplicated_singleton_is_rejected(builder, validator) -> None:
    blob = {
        "node_type": "group",
        "id": "dup",
        "nodes": [
            {
                "node_type": "action",
                "id": "b1",
                "family": "contextualize",
                "kind": "breadcrumb",
                "config": {},
            },
            {
                "node_type": "action",
                "id": "b2",
                "family": "contextualize",
                "kind": "breadcrumb",
                "config": {},
            },
        ],
        "transitions": [{"from_node_id": "b1", "to_node_id": "b2"}],
        "bindings": {
            "b1": {"chunks": {"source": "run", "field_name": "chunks"}},
            "b2": {"chunks": {"source": "node", "node_id": "b1", "field_name": "chunks"}},
        },
    }
    codes = {issue.code.value for issue in validator.validate(builder.build(blob))}
    assert "duplicate_unique_node" in codes
