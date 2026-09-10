"""SearchRunner's BuiltGraphPool: the stock search graph is built + validated ONCE across many
requests (the W2-01 hot-path fix), a DISTINCT blob builds its own graph, and concurrent runs on
different collections never cross-bind their read ports.

All HTTP-free: a fake embedder the encode node rebuilds from the contract, and mock read ports that
return fixed candidates — no Qdrant, no Postgres, no network. The pool caches the immutable build +
validate work; the read port stays bound PER RUN (the mutable seam the pool must not share).
"""

import asyncio
from unittest.mock import patch

from shared_libs.pipelines.ingest.estimate import RateTable
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.pipelines.search import CollectionReadPort, SearchPipeline
from shared_libs.public_models.search import (
    Candidate,
    Hit,
    QueryFilters,
    RawQuery,
    SearchContract,
)


# ---------------------- Test doubles ---------------------- #
class _FakePoolEmbedConfig(BaseEmbedConfig):
    """Config of the HTTP-free test embedder used by the pool tests."""


@NodeRegistry.register("embed")
class FakePoolEmbedNode(BaseEmbedderNode):
    """A deterministic, HTTP-free embedder the encode node rebuilds from the contract."""

    KIND = (
        "fake_pool_embed"  # 'fake_' prefix: skipped by the design-surface test, never in a palette
    )
    NAME = "Fake pool embedder"
    SUMMARY = "Deterministic embedder for the graph-pool tests (no HTTP)."
    Config = _FakePoolEmbedConfig

    async def _embed_dense(self, texts: list[str]) -> list[list[float]]:
        """A fixed 4-d dense vector per text — no network."""
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class _FixedReadPort(CollectionReadPort):
    """A read port returning ONE candidate carrying a caller-chosen id — proves which port was used."""

    def __init__(self, chunk_id: str, *, yield_first: bool = False) -> None:
        self._chunk_id = chunk_id
        self._yield_first = yield_first

    async def hybrid_search(self, encoded, filters, limit, targets=None, fusion="rrf"):
        # Optionally yield control so two gathered runs are genuinely in-flight at once.
        if self._yield_first:
            await asyncio.sleep(0.01)
        return [Candidate(chunk_id=self._chunk_id, score=0.9, source="hybrid")]

    async def hydrate(self, chunk_ids):
        return {
            chunk_id: Hit(chunk_id=chunk_id, document_id="doc", text="t", metadata={})
            for chunk_id in chunk_ids
        }


def _run_input() -> dict:
    """The minimal search run-input wired to the fake embedder."""
    return {
        "query": RawQuery(text="hello world", top_k=3, flags={}),
        "filters": QueryFilters(filters={}),
        "contract": SearchContract(
            collection_id="col-1",
            embed_kind="fake_pool_embed",
            embed_config={"model": "fake", "embed_sparse": False},
        ),
    }


def _runner():
    """A fresh SearchRunner (its own empty pool) — deferred import after sys.path wiring."""
    from backend.libs.search.runner import SearchRunner  # noqa: PLC0415

    return SearchRunner()


# ---------------------- Tests ---------------------- #
def test_stock_graph_is_built_and_validated_once_across_many_runs() -> None:
    """N sequential runs on the same graph_key build + validate the graph exactly ONCE (the fix)."""
    runner = _runner()
    blob = SearchPipeline.default_blob().model_dump(mode="json")
    rates = RateTable.from_overrides(None)

    with (
        patch.object(runner._builder, "build", wraps=runner._builder.build) as spy_build,
        patch.object(runner._validator, "validate", wraps=runner._validator.validate) as spy_val,
    ):
        for _ in range(5):
            result, _usage = asyncio.run(
                runner.run(
                    blob,
                    _run_input(),
                    _FixedReadPort("c1"),
                    rates,
                    graph_key="stock-default",
                    timeout_seconds=30,
                )
            )
            assert [hit.chunk_id for hit in result.hits] == ["c1"]

    # 1. Five runs, but the expensive build + validate each happened exactly once.
    assert spy_build.call_count == 1, spy_build.call_count
    assert spy_val.call_count == 1, spy_val.call_count


def test_a_distinct_blob_key_builds_its_own_graph() -> None:
    """A different graph_key is a different blob → it builds once on its own (per-blob correctness)."""
    runner = _runner()
    default_blob = SearchPipeline.default_blob().model_dump(mode="json")
    rerank_blob = SearchPipeline.rerank_blob().model_dump(mode="json")
    rates = RateTable.from_overrides(None)

    with patch.object(runner._builder, "build", wraps=runner._builder.build) as spy_build:
        # Two runs on the default key → built once.
        for _ in range(2):
            asyncio.run(
                runner.run(
                    default_blob,
                    _run_input(),
                    _FixedReadPort("c1"),
                    rates,
                    graph_key="k-default",
                    timeout_seconds=30,
                )
            )
        # A run on a DISTINCT key (a genuinely different blob) → a second build.
        asyncio.run(
            runner.run(
                rerank_blob,
                _run_input(),
                _FixedReadPort("c1"),
                rates,
                graph_key="k-rerank",
                timeout_seconds=30,
            )
        )

    assert spy_build.call_count == 2, spy_build.call_count


def test_concurrent_runs_on_the_same_key_do_not_cross_bind_read_ports() -> None:
    """Two in-flight runs sharing a key each keep their OWN read port — no pooled-graph leak.

    If the pool shared one bound graph, the later bind would overwrite the earlier run's read port
    and one collection's search would read the other's store. Each run must deliver ITS port's hit.
    """
    runner = _runner()
    blob = SearchPipeline.default_blob().model_dump(mode="json")
    rates = RateTable.from_overrides(None)

    async def _both() -> tuple[list[str], list[str]]:
        run_a = runner.run(
            blob,
            _run_input(),
            _FixedReadPort("from-A", yield_first=True),
            rates,
            graph_key="shared",
            timeout_seconds=30,
        )
        run_b = runner.run(
            blob,
            _run_input(),
            _FixedReadPort("from-B", yield_first=True),
            rates,
            graph_key="shared",
            timeout_seconds=30,
        )
        (res_a, _), (res_b, _) = await asyncio.gather(run_a, run_b)
        return [h.chunk_id for h in res_a.hits], [h.chunk_id for h in res_b.hits]

    hits_a, hits_b = asyncio.run(_both())

    # 1. Each run delivered exactly its OWN port's candidate — no cross-binding.
    assert hits_a == ["from-A"], hits_a
    assert hits_b == ["from-B"], hits_b


def test_graph_is_returned_to_the_pool_after_a_run() -> None:
    """A completed run releases its graph so the NEXT run reuses it (the free list is non-empty)."""
    runner = _runner()
    blob = SearchPipeline.default_blob().model_dump(mode="json")
    rates = RateTable.from_overrides(None)

    asyncio.run(
        runner.run(
            blob, _run_input(), _FixedReadPort("c1"), rates, graph_key="reused", timeout_seconds=30
        )
    )

    # 1. The pool kept the built graph warm under its key for the next request to reuse.
    assert len(runner._pool._free.get("reused", [])) == 1
