"""AddNode + AddLoop: chaining from the terminal, auto-wiring, id minting."""

from shared_libs.pipelines.base import FromNode, FromRunInput
from shared_libs.pipelines.build import ActionNodeBlob, GroupNodeBlob
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.edit import AddLoop, AddNode


def test_add_node_chains_from_terminal_and_auto_wires_unambiguous_slot(editor) -> None:
    blob = GroupNodeBlob(
        id="aw",
        nodes=[ActionNodeBlob(id="probe", family="intake", kind="format_probe")],
        bindings={"probe": {"source": FromRunInput(field_name="source")}},
    )
    added = editor.apply(blob, [AddNode(family="intake", kind="admission")])

    assert any(n.id == "admission" for n in added.nodes), "id derived from kind"
    assert any(t.from_node_id == "probe" and t.to_node_id == "admission" for t in added.transitions)
    admit_binds = added.bindings["admission"]
    assert isinstance(admit_binds["probe"], FromNode)
    assert admit_binds["probe"].node_id == "probe"
    assert admit_binds["probe"].field_name == "probe"
    assert "source" not in admit_binds and "contract" not in admit_binds
    # The input blob is never mutated.
    assert blob.bindings.get("admission") is None


def test_add_node_with_explicit_id(editor) -> None:
    blob = GroupNodeBlob(
        id="root", nodes=[ActionNodeBlob(id="probe", family="intake", kind="format_probe")]
    )
    added = editor.apply(blob, [AddNode(family="intake", kind="admission", node_id="my_admit")])
    assert any(n.id == "my_admit" for n in added.nodes)


def test_add_loop_appends_a_foreach_chained_from_terminal(editor, builder, validator) -> None:
    blob = GroupNodeBlob(
        id="root",
        nodes=[
            ActionNodeBlob(id="probe", family="intake", kind="format_probe"),
        ],
        bindings={"probe": {"source": FromRunInput(field_name="source")}},
    )
    added = editor.apply(
        blob,
        [
            AddLoop(
                over=FromNode(node_id="probe", field_name="probe"),
                item_field="item",
                node_id="loop",
            )
        ],
    )
    loop = next(n for n in added.nodes if n.id == "loop")
    assert isinstance(loop, ForEachNodeBlob)
    assert loop.item_field == "item"
    assert any(t.from_node_id == "probe" and t.to_node_id == "loop" for t in added.transitions)
    # An empty body is expected here (the caller populates it with further ops) — not validated.


def test_add_loop_derives_id_from_loop_base(editor) -> None:
    blob = GroupNodeBlob(
        id="root", nodes=[ActionNodeBlob(id="probe", family="intake", kind="format_probe")]
    )
    added = editor.apply(
        blob, [AddLoop(over=FromNode(node_id="probe", field_name="probe"), item_field="x")]
    )
    assert any(n.id == "loop" for n in added.nodes)
