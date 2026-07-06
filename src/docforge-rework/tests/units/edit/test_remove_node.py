"""RemoveNode: bridging a single-in/single-out chain, purging dangling references."""

from shared_libs.pipelines.base import FromNode, FromRunInput, Transition
from shared_libs.pipelines.build import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.edit import RemoveNode

from .conftest import issues_of


def test_remove_optional_slot_bridges_and_purges_dangling_ref(editor, builder, validator, default_blob) -> None:
    assert issues_of(builder, validator, default_blob) == [], "the stock blob must start healthy"
    pruned = editor.apply(default_blob, [RemoveNode(node_id="meta_doc")])

    assert not any(n.id == "meta_doc" for n in pruned.nodes)
    assert any(t.from_node_id == "meta_chunk" and t.to_node_id == "embed" for t in pruned.transitions)
    assert "document_meta" not in pruned.bindings["bundle"]
    assert issues_of(builder, validator, pruned) == []


def test_remove_node_purging_a_required_slot_surfaces_missing_binding(editor, builder, validator) -> None:
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
