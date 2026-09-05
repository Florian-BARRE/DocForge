"""ForEach body-group ids are part of the id-uniqueness scans (mint + fragment remap), so a minted
or remapped id can never collide with a ForEach body's OWN id (e.g. ``loop_body``). Before the fix
``all_node_ids`` / the fragment scan walked a ForEach's body NODES but skipped the body group's own
id, letting a fresh/remapped id land on it."""

import pytest

from shared_libs.pipelines.base import FromRunInput
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
)
from shared_libs.pipelines.edit import AddNode, EditError, InsertFragment
from shared_libs.pipelines.edit.topology import BlobTopology

_BODY_ID = "loop_body"


def _blob_with_foreach_body(body_id: str = _BODY_ID) -> GroupNodeBlob:
    """A graph carrying a ForEach whose body group has the id ``body_id``."""
    return GroupNodeBlob(
        id="root",
        nodes=[
            ActionNodeBlob(id="seed", family="enrich", kind="figure_entry"),
            ForEachNodeBlob(
                id="loop",
                over=FromRunInput(field_name="figures"),
                item_field="figure",
                body=GroupNodeBlob(
                    id=body_id,
                    nodes=[ActionNodeBlob(id="inner", family="enrich", kind="figure_entry")],
                ),
            ),
        ],
    )


def test_all_node_ids_includes_the_foreach_body_id() -> None:
    ids = BlobTopology.all_node_ids(_blob_with_foreach_body())
    assert _BODY_ID in ids
    assert {"seed", "loop", "inner"} <= ids


def test_fresh_id_never_returns_a_foreach_body_id() -> None:
    """Deriving a fresh id from the body's stem must skip the body id itself."""
    assert BlobTopology.fresh_id(_blob_with_foreach_body(), _BODY_ID) != _BODY_ID


def test_add_node_with_explicit_body_id_is_rejected(editor) -> None:
    """Minting a node whose explicit id equals a ForEach body id is a duplicate, not a silent clash."""
    with pytest.raises(EditError, match=_BODY_ID):
        editor.apply(
            _blob_with_foreach_body(),
            [AddNode(family="enrich", kind="figure_entry", node_id=_BODY_ID)],
        )


def test_fragment_remap_avoids_the_foreach_body_id(editor) -> None:
    """A spliced fragment node whose id equals the target's ForEach body id is remapped away, so the
    body group keeps its id and the incoming node gets a suffixed one."""
    fragment = GroupNodeBlob(
        id="frag",
        nodes=[ActionNodeBlob(id=_BODY_ID, family="enrich", kind="figure_entry")],
    )
    edited = editor.apply(_blob_with_foreach_body(), [InsertFragment(fragment=fragment)])
    ids = BlobTopology.all_node_ids(edited)
    # The original ForEach body id is untouched; the fragment node was suffixed to dodge it.
    assert _BODY_ID in ids
    assert f"{_BODY_ID}_2" in ids
