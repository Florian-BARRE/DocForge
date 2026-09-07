"""RecordTrace.summarize — the cheap SHAPE descriptor a node payload gets at the always-on trace
tier. Pins the exact keys the shape descriptor emits for a model / list / scalar payload, that it
never leaks raw content (only sizes/counts), and that its fingerprint is deterministic per shape."""

from shared_libs.pipelines.engine import RecordTrace

from .conftest import Doc


def test_model_summary_has_the_exact_shape_keys() -> None:
    """A pydantic Artifact summarizes to {type, fields, sizes, item_count, hash} — no content."""
    descriptor = RecordTrace.summarize(Doc(text="hello"))

    assert set(descriptor.keys()) == {"type", "fields", "sizes", "item_count", "hash"}
    assert descriptor["type"] == "Doc"
    assert descriptor["fields"] == ["text"]
    # The str field's LENGTH is captured, never its content — shallow, not a deep model_dump.
    assert descriptor["sizes"] == {"text": 5}
    assert descriptor["item_count"] == {}
    assert isinstance(descriptor["hash"], str) and len(descriptor["hash"]) == 64
    # The raw content never leaks into the descriptor (it stays a shape/size fingerprint, not a copy).
    assert "hello" not in descriptor.values()
    assert "hello" not in descriptor["sizes"]


def test_model_summary_hash_is_deterministic_for_identical_shape() -> None:
    """Two payloads of identical shape/size share their fingerprint — a stable content-free hash."""
    first = RecordTrace.summarize(Doc(text="hello"))
    second = RecordTrace.summarize(Doc(text="world"))  # same length, different content
    assert first["hash"] == second["hash"]


def test_model_summary_hash_differs_for_a_different_shape() -> None:
    """A payload of a different size fingerprints differently (the shape/size actually changed)."""
    short = RecordTrace.summarize(Doc(text="hi"))
    long = RecordTrace.summarize(Doc(text="hello world, this is much longer"))
    assert short["hash"] != long["hash"]


def test_list_summary_reports_length_and_element_type() -> None:
    """A list[Artifact] payload (a ForEach items slot) summarizes to length + element type — never
    per-item content — and does not require running a ForEach graph to exercise."""
    descriptor = RecordTrace.summarize([Doc(text="a"), Doc(text="b"), Doc(text="c")])

    assert descriptor["type"] == "list"
    assert descriptor["item_count"] == 3
    assert descriptor["element_type"] == "Doc"
    assert set(descriptor.keys()) == {"type", "item_count", "element_type", "hash"}


def test_empty_list_summary_has_no_element_type() -> None:
    """An empty list carries no element sample to type — element_type degrades to None, not a crash."""
    descriptor = RecordTrace.summarize([])
    assert descriptor == {
        "type": "list",
        "item_count": 0,
        "element_type": None,
        "hash": descriptor["hash"],
    }


def test_list_summary_hash_differs_by_length() -> None:
    """Two lists of different length fingerprint differently (the shape actually changed)."""
    two = RecordTrace.summarize([Doc(text="a"), Doc(text="b")])
    three = RecordTrace.summarize([Doc(text="a"), Doc(text="b"), Doc(text="c")])
    assert two["hash"] != three["hash"]


def test_scalar_summary_reports_type_and_size() -> None:
    """A scalar string payload summarizes to its type + length — content-free."""
    descriptor = RecordTrace.summarize("hello world")
    assert descriptor["type"] == "str"
    assert descriptor["sizes"] == {"value": 11}
    assert "hello world" not in descriptor.values()


def test_scalar_summary_of_a_non_sized_value_has_no_sizes_key() -> None:
    """An int/None scalar has no byte/char size to report — ``sizes`` is simply absent."""
    descriptor = RecordTrace.summarize(42)
    assert descriptor["type"] == "int"
    assert "sizes" not in descriptor
