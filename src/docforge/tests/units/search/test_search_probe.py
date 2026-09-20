"""The pure SearchRetrievalProbe accumulator (slice 1A): axes classification per call, the filter
flag, accumulation across multiple calls (the ForEach-over-sub-queries case), and the retrieval-order
cap that keeps memory bounded whatever candidate_k a stored blob asks for."""

from backend.libs.search.probe import (
    AXES_DENSE_ONLY,
    AXES_DENSE_SPARSE,
    AXES_NONE,
    AXES_SPARSE_ONLY,
    SearchRetrievalProbe,
)


def test_record_call_accumulates_axes_filter_and_candidate_totals() -> None:
    """Each call appends its bounded axes value + filter flag and sums the candidate count."""
    probe = SearchRetrievalProbe()
    probe.record_call(AXES_DENSE_SPARSE, True, ["a", "b", "c"])
    probe.record_call(AXES_DENSE_ONLY, False, ["d"])

    assert probe.calls == 2
    assert probe.candidates_total == 4
    assert probe.axes == [AXES_DENSE_SPARSE, AXES_DENSE_ONLY]
    assert probe.filtered == [True, False]


def test_all_four_axes_values_are_representable() -> None:
    """The bounded axes enum covers dense+sparse, dense-only, sparse-only and the filter-only none."""
    probe = SearchRetrievalProbe()
    for axes in (AXES_DENSE_SPARSE, AXES_DENSE_ONLY, AXES_SPARSE_ONLY, AXES_NONE):
        probe.record_call(axes, False, [])
    assert probe.axes == [AXES_DENSE_SPARSE, AXES_DENSE_ONLY, AXES_SPARSE_ONLY, AXES_NONE]


def test_retrieval_order_is_capped() -> None:
    """The recorded retrieval order never grows past the cap, whatever candidate_k asks for."""
    probe = SearchRetrievalProbe()
    probe.record_call(AXES_DENSE_SPARSE, False, [str(i) for i in range(500)])
    assert len(probe.retrieval_order) == 200
    # A second call adds nothing once the cap is reached (room is exhausted).
    probe.record_call(AXES_DENSE_SPARSE, False, ["x"])
    assert len(probe.retrieval_order) == 200


def test_record_branches_unions_across_calls() -> None:
    """Branch id sets union across calls (the ForEach case) and count the successful probe."""
    probe = SearchRetrievalProbe()
    probe.record_branches({"a", "b"}, {"b", "c"})
    probe.record_branches({"d"}, {"e"})
    assert probe.dense_ids == {"a", "b", "d"}
    assert probe.sparse_ids == {"b", "c", "e"}
    assert probe.branch_probe_ok == 2
