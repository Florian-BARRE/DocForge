"""Dense/sparse fusion breakdown (slice 1B), OFF by default. Serviceless — a spy Database records
every hybrid_ids call. The headline guard: measure_branch_contribution=False ⇒ EXACTLY one Qdrant
query (zero behavioural difference). ON ⇒ two extra concurrent branch probes (dense-only / sparse-
only), best-effort (a probe failure never fails the search, never records a breakdown)."""

import asyncio
import uuid

import pytest

from backend.libs.search.read_port import CollectionReadPortImpl
from shared_libs.public_models.embed import SparseVector
from shared_libs.public_models.search import EncodedQuery, SearchTarget


# ---------------------- Spy Database ---------------------- #
class _SpySearchFacade:
    """Records every hybrid_ids call; returns branch-specific pools so a breakdown is checkable."""

    def __init__(self, *, fail_probes: bool = False) -> None:
        self.calls: list[dict] = []
        self._fail_probes = fail_probes

    async def hybrid_ids(
        self,
        collection_id,
        *,
        dense=None,
        sparse=None,
        conditions=(),
        limit=10,
        prefetch_limit=None,
        fusion="rrf",
        max_disabled_exclusions=None,
    ):
        """Return a pool keyed by which branches were queried (both / dense-only / sparse-only)."""
        self.calls.append(
            {
                "dense": dense,
                "sparse": sparse,
                "conditions": conditions,
                "limit": limit,
                "fusion": fusion,
            }
        )
        both = bool(dense) and bool(sparse)
        if not both and self._fail_probes:
            raise RuntimeError("probe query blew up")
        if both:  # the authoritative fused call
            return [("c1", 0.9), ("c2", 0.7), ("c3", 0.5)]
        if dense:  # dense-only probe
            return [("c1", 0.8), ("c2", 0.6)]
        return [("c2", 0.4), ("c3", 0.3)]  # sparse-only probe


class _FakeDatabase:
    """Minimal Database stand-in exposing only the search facade the read port uses."""

    def __init__(self, search: _SpySearchFacade) -> None:
        self.search = search


def _both_axes_query() -> tuple[EncodedQuery, list[SearchTarget]]:
    """An encoded query + a content target that resolves to BOTH the dense and sparse axes."""
    encoded = EncodedQuery(
        dense=[0.1, 0.2, 0.3, 0.4],
        sparse=SparseVector(indices=[1, 2], values=[0.5, 0.5]),
        model="fake",
    )
    return encoded, [SearchTarget(field="content", semantic=True, lexical=True)]


# ---------------------- Tests ---------------------- #
def test_flag_off_issues_exactly_one_query() -> None:
    """The headline guard: with the knob OFF, retrieval issues EXACTLY one Qdrant query."""
    spy = _SpySearchFacade()
    port = CollectionReadPortImpl(_FakeDatabase(spy), uuid.uuid4())
    encoded, targets = _both_axes_query()

    candidates = asyncio.run(port.hybrid_search(encoded, filters={}, limit=10, targets=targets))
    assert len(spy.calls) == 1  # no probes fired
    assert [c.chunk_id for c in candidates] == ["c1", "c2", "c3"]
    assert port.probe.dense_ids is None and port.probe.sparse_ids is None


def test_flag_on_fires_two_branch_probes_with_matching_scope() -> None:
    """ON ⇒ 3 calls: the fused call + a dense-only (sparse=None) + a sparse-only (dense=None)."""
    spy = _SpySearchFacade()
    port = CollectionReadPortImpl(_FakeDatabase(spy), uuid.uuid4())
    encoded, targets = _both_axes_query()

    asyncio.run(
        port.hybrid_search(
            encoded,
            filters={"k": "v"},
            limit=25,
            targets=targets,
            measure_branch_contribution=True,
        )
    )
    assert len(spy.calls) == 3
    dense_only = [c for c in spy.calls if c["dense"] and c["sparse"] is None]
    sparse_only = [c for c in spy.calls if c["sparse"] and c["dense"] is None]
    assert len(dense_only) == 1 and len(sparse_only) == 1
    # Every probe shares the authoritative call's scope so the pools are comparable.
    for call in spy.calls:
        assert call["limit"] == 25
        assert call["conditions"] == spy.calls[0]["conditions"]
    # The per-branch id sets are recorded on the probe for the emitter.
    assert port.probe.dense_ids == {"c1", "c2"}
    assert port.probe.sparse_ids == {"c2", "c3"}
    assert port.probe.branch_probe_ok == 1


def test_single_axis_query_never_probes_even_when_enabled() -> None:
    """A dense-only encoded query has a trivial breakdown → no probe fires even with the knob ON."""
    spy = _SpySearchFacade()
    port = CollectionReadPortImpl(_FakeDatabase(spy), uuid.uuid4())
    encoded = EncodedQuery(dense=[0.1, 0.2], sparse=None, model="fake")
    targets = [SearchTarget(field="content", semantic=True, lexical=True)]

    asyncio.run(
        port.hybrid_search(
            encoded, filters={}, limit=10, targets=targets, measure_branch_contribution=True
        )
    )
    assert len(spy.calls) == 1
    assert port.probe.dense_ids is None


def test_probe_failure_never_fails_the_search() -> None:
    """A raising probe leaves the authoritative hits intact + records the probe error, no breakdown."""
    spy = _SpySearchFacade(fail_probes=True)
    port = CollectionReadPortImpl(_FakeDatabase(spy), uuid.uuid4())
    encoded, targets = _both_axes_query()

    candidates = asyncio.run(
        port.hybrid_search(
            encoded, filters={}, limit=10, targets=targets, measure_branch_contribution=True
        )
    )
    # The authoritative fused hits are returned unchanged...
    assert [c.chunk_id for c in candidates] == ["c1", "c2", "c3"]
    # ...the breakdown is skipped, and the probe failure is counted (never silent).
    assert port.probe.dense_ids is None
    assert port.probe.branch_probe_error == 1
    assert port.probe.branch_probe_ok == 0


def test_extra_config_field_is_rejected_at_build() -> None:
    """extra='forbid' still bites: an unknown retrieve config field fails the config model."""
    from shared_libs.pipelines.search.nodes.retrieve.hybrid.core import RetrieveHybridConfig

    with pytest.raises(Exception):
        RetrieveHybridConfig(measure_branch_contribution=True, bogus_field=1)
