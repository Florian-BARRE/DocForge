"""EditError paths shared across operations: unknown kind, duplicate id, unknown container path."""

from shared_libs.pipelines.edit import AddNode, EditError, RemoveNode


def test_unknown_kind_raises_with_the_kind_named(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [AddNode(family="ocr", kind="does_not_exist")])
        raise AssertionError("unknown kind must raise EditError")
    except EditError as exc:
        assert "does_not_exist" in str(exc)


def test_duplicate_explicit_id_raises_with_the_id_named(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [AddNode(family="intake", kind="format_probe", node_id="probe")])
        raise AssertionError("duplicate explicit id must raise EditError")
    except EditError as exc:
        assert "duplicate" in str(exc) and "probe" in str(exc)


def test_unknown_container_path_raises(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [RemoveNode(node_id="chunk", container=["ghost_container"])])
        raise AssertionError("an unknown container path must raise EditError")
    except EditError as exc:
        assert "ghost_container" in str(exc)


def test_remove_unknown_node_raises_edit_error(editor, default_blob) -> None:
    try:
        editor.apply(default_blob, [RemoveNode(node_id="ghost")])
        raise AssertionError("removing an unknown node must raise EditError")
    except EditError as exc:
        assert "ghost" in str(exc)


def test_apply_a_family_with_no_action_nodes_is_rejected(editor, default_blob) -> None:
    """Attempting to add a non-ActionNode family kind must raise, never silently misbuild."""
    try:
        editor.apply(default_blob, [AddNode(family="deliver", kind="does_not_exist")])
        raise AssertionError("unknown kind in a real family must still raise EditError")
    except EditError as exc:
        assert "does_not_exist" in str(exc)
