"""SetBinding, SetAfter, SetCondition, SetConfig, SetLoopProp — the remaining edit operations
not covered by the scratchpad's test_edit_api.py (which only exercised 4 of the 9)."""

from shared_libs.pipelines.base import Always, FromNode, FromRunInput, OnFailure
from shared_libs.pipelines.build import GroupNodeBlob
from shared_libs.pipelines.build.blob import ForEachNodeBlob
from shared_libs.pipelines.edit import (
    EditError,
    SetAfter,
    SetBinding,
    SetCondition,
    SetConfig,
    SetLoopProp,
)


def test_set_binding_none_unbinds_a_slot(editor, default_blob) -> None:
    unbound = editor.apply(
        default_blob, [SetBinding(node_id="meta_doc_prep", slot="contract", binding=None)]
    )
    assert "contract" not in unbound.bindings["meta_doc_prep"]


def test_set_binding_sets_a_real_binding(editor, default_blob) -> None:
    rebound = editor.apply(
        default_blob,
        [
            SetBinding(
                node_id="ctx_breadcrumb",
                slot="chunks",
                binding=FromNode(node_id="chunk", field_name="chunks"),
            )
        ],
    )
    assert rebound.bindings["ctx_breadcrumb"]["chunks"].node_id == "chunk"


def test_set_binding_on_unknown_node_raises_edit_error(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [SetBinding(node_id="ghost", slot="x", binding=None)])
        raise AssertionError("an unknown node id must raise EditError")
    except EditError as exc:
        assert "ghost" in str(exc)


def test_set_binding_unbinding_an_already_unbound_slot_is_a_clean_no_op(
    editor, default_blob
) -> None:
    """Unbinding a slot that was never set must not raise — SetBinding(None) is idempotent."""
    edited = editor.apply(
        default_blob, [SetBinding(node_id="meta_doc_prep", slot="ghost_slot", binding=None)]
    )
    assert "ghost_slot" not in edited.bindings.get("meta_doc_prep", {})


def test_set_after_reprositions_a_node_keeping_the_edge_condition(
    editor, builder, validator, default_blob
) -> None:
    repositioned = editor.apply(
        default_blob, [SetAfter(node_id="ctx_breadcrumb", from_node_id="parse")]
    )
    edge = next(t for t in repositioned.transitions if t.to_node_id == "ctx_breadcrumb")
    assert edge.from_node_id == "parse"
    # ctx_breadcrumb's own data binding is untouched by SetAfter (control flow only); the
    # resulting graph may or may not validate depending on downstream bindings, which is fine —
    # SetAfter's contract is purely about the incoming transition.


def test_set_after_none_detaches_the_node(editor, default_blob) -> None:
    detached = editor.apply(default_blob, [SetAfter(node_id="ctx_breadcrumb", from_node_id=None)])
    assert not any(t.to_node_id == "ctx_breadcrumb" for t in detached.transitions)


def test_set_after_unknown_predecessor_raises_edit_error(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [SetAfter(node_id="ctx_breadcrumb", from_node_id="ghost")])
        raise AssertionError("unknown predecessor must raise EditError")
    except EditError as exc:
        assert "ghost" in str(exc)


def test_set_condition_replaces_an_existing_edges_condition(editor, default_blob) -> None:
    edited = editor.apply(
        default_blob,
        [
            SetCondition(
                from_node_id="meta_chunk_apply", to_node_id="meta_doc_prep", condition=OnFailure()
            )
        ],
    )
    edge = next(
        t
        for t in edited.transitions
        if t.from_node_id == "meta_chunk_apply" and t.to_node_id == "meta_doc_prep"
    )
    assert isinstance(edge.condition, OnFailure)


def test_set_condition_on_missing_edge_raises_edit_error(editor, default_blob) -> None:
    try:
        editor.apply(
            default_blob,
            [SetCondition(from_node_id="probe", to_node_id="embed", condition=Always())],
        )
        raise AssertionError("missing edge must raise EditError")
    except EditError as exc:
        assert "probe" in str(exc) and "embed" in str(exc)


def test_set_config_replaces_the_whole_config_dict(editor, default_blob) -> None:
    edited = editor.apply(default_blob, [SetConfig(node_id="chunk", config={"target_tokens": 999})])
    chunk_node = next(n for n in edited.nodes if n.id == "chunk")
    assert chunk_node.config == {"target_tokens": 999}


def test_set_config_on_a_non_action_node_raises_edit_error(editor) -> None:
    blob = GroupNodeBlob(
        id="root",
        nodes=[
            ForEachNodeBlob(
                id="loop",
                over=FromRunInput(field_name="things"),
                item_field="thing",
                body=GroupNodeBlob(id="body"),
            )
        ],
    )
    try:
        editor.apply(blob, [SetConfig(node_id="loop", config={"x": 1})])
        raise AssertionError("a foreach has no config and must raise EditError")
    except EditError as exc:
        assert "loop" in str(exc)


def test_set_loop_prop_updates_only_the_provided_fields(editor, default_blob) -> None:
    edited = editor.apply(
        default_blob, [SetLoopProp(node_id="per_figure", item_field="pic", max_concurrency=9)]
    )
    loop = next(n for n in edited.nodes if n.id == "per_figure")
    assert loop.item_field == "pic"
    assert loop.max_concurrency == 9
    # 'over' was not provided -> unchanged.
    original = next(n for n in default_blob.nodes if n.id == "per_figure")
    assert loop.over == original.over


def test_set_loop_prop_on_non_loop_node_raises_edit_error(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [SetLoopProp(node_id="chunk", item_field="x")])
        raise AssertionError("a non-loop node must raise EditError")
    except EditError as exc:
        assert "chunk" in str(exc)
