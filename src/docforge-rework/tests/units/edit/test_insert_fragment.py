"""InsertFragment: id collision suffixing, root chaining, FromFirst remap on the 2nd copy."""

from shared_libs.pipelines.edit import InsertFragment

from .conftest import issues_of

_FRAGMENT = {
    "node_type": "group",
    "id": "ocr_escalation",
    "nodes": [
        {"node_type": "action", "id": "ocr_cheap", "family": "ocr", "kind": "rapidocr", "config": {}},
        {"node_type": "action", "id": "ocr_robust", "family": "ocr", "kind": "mistral", "config": {"api_key": "SET_ME"}},
        {
            "node_type": "action",
            "id": "describe",
            "family": "vlm",
            "kind": "openai_compatible",
            "config": {"base_url": "http://vlm:8000/v1", "model": "SET_ME"},
        },
    ],
    "transitions": [
        {"from_node_id": "ocr_cheap", "to_node_id": "ocr_robust", "condition": {"kind": "score_below", "threshold": 0.5}},
        {"from_node_id": "ocr_cheap", "to_node_id": "ocr_robust", "condition": {"kind": "on_failure"}},
        {"from_node_id": "ocr_cheap", "to_node_id": "describe"},
        {"from_node_id": "ocr_robust", "to_node_id": "describe"},
    ],
    "bindings": {
        "ocr_cheap": {"figure": {"source": "group", "field_name": "figure"}},
        "ocr_robust": {"figure": {"source": "group", "field_name": "figure"}},
        "describe": {
            "figure": {
                "source": "first",
                "candidates": [
                    {"source": "node", "node_id": "ocr_robust", "field_name": "figure"},
                    {"source": "node", "node_id": "ocr_cheap", "field_name": "figure"},
                ],
            }
        },
    },
}


def test_insert_once_chains_the_fragment_root_and_validates(editor, builder, validator, default_blob) -> None:
    once = editor.apply(default_blob, [InsertFragment(fragment=_FRAGMENT)])
    assert {"ocr_cheap", "ocr_robust", "describe"} <= {n.id for n in once.nodes}
    assert any(t.from_node_id == "bundle" and t.to_node_id == "ocr_cheap" for t in once.transitions)
    assert issues_of(builder, validator, once) == []


def test_insert_twice_suffixes_ids_and_remaps_from_first(editor, builder, validator, default_blob) -> None:
    twice = editor.apply(default_blob, [InsertFragment(fragment=_FRAGMENT), InsertFragment(fragment=_FRAGMENT)])
    twice_ids = {n.id for n in twice.nodes}
    assert {"ocr_cheap_2", "ocr_robust_2", "describe_2"} <= twice_ids

    join = twice.bindings["describe_2"]["figure"]
    assert {c.node_id for c in join.candidates} == {"ocr_robust_2", "ocr_cheap_2"}
    assert issues_of(builder, validator, twice) == []
