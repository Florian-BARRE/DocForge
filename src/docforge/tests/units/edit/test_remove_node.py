"""RemoveNode: bridging a single-in/single-out chain, purging dangling references."""

import pytest

from shared_libs.pipelines.base import FromNode, FromRunInput, Transition
from shared_libs.pipelines.build import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.edit import EditError, RemoveNode

from .conftest import issues_of


def test_remove_optional_slot_bridges_and_purges_dangling_ref(
    editor, builder, validator, full_blob
) -> None:
    assert issues_of(builder, validator, full_blob) == [], "the stock blob must start healthy"
    pruned = editor.apply(full_blob, [RemoveNode(node_id="meta_doc_apply")])

    assert not any(n.id == "meta_doc_apply" for n in pruned.nodes)
    assert any(
        t.from_node_id == "meta_doc_loop" and t.to_node_id == "embed" for t in pruned.transitions
    )
    assert "document_meta" not in pruned.bindings["bundle"]
    assert issues_of(builder, validator, pruned) == []


def test_remove_node_purging_a_required_slot_surfaces_missing_binding(
    editor, builder, validator
) -> None:
    blob = GroupNodeBlob(
        id="req",
        nodes=[
            ActionNodeBlob(id="p", family="intake", kind="format_probe"),
            ActionNodeBlob(id="a", family="intake", kind="admission"),
        ],
        transitions=[Transition(from_node_id="p", to_node_id="a")],
        bindings={
            "p": {"source": FromRunInput(field_name="source")},
            "a": {
                "source": FromRunInput(field_name="source"),
                "probe": FromNode(node_id="p", field_name="probe"),
                "contract": FromRunInput(field_name="contract"),
            },
        },
    )
    assert issues_of(builder, validator, blob) == [], "the minimal p->a blob must start healthy"
    lost = editor.apply(blob, [RemoveNode(node_id="p")])
    assert "probe" not in lost.bindings.get("a", {})
    issues = issues_of(builder, validator, lost)
    assert any(i.code == "missing_binding" and "probe" in i.message for i in issues)


def test_remove_node_a_sibling_foreach_iterates_over_is_refused(editor) -> None:
    """A ForEach's ``over`` is a required binding __purge_references cannot heal — so removing the
    node it iterates over is REFUSED (mirroring set_after), never left as a dangling ``over``."""
    blob = GroupNodeBlob(
        id="root",
        nodes=[
            ActionNodeBlob(id="seed", family="intake", kind="format_probe"),
            ForEachNodeBlob(
                id="loop",
                over=FromNode(node_id="seed", field_name="probe"),
                item_field="item",
                body=GroupNodeBlob(
                    id="loop_body",
                    nodes=[ActionNodeBlob(id="inner", family="enrich", kind="figure_entry")],
                ),
            ),
        ],
        transitions=[Transition(from_node_id="seed", to_node_id="loop")],
    )
    with pytest.raises(EditError, match="loop"):
        editor.apply(blob, [RemoveNode(node_id="seed")])
