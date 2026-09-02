"""The engine's stage-cache seam (FlowEngine + RunContext.cache_hook).

Proves the pure-engine contract: with NO hook the run is byte-for-byte unchanged; with a hook the
engine consults it ONLY at a cacheable ROOT node — a HIT skips ``node.run`` and serves the stored
artefact (so a fresh downstream stage runs on it), a MISS runs the node then hands the output to the
hook to store. A cacheable node nested in a sub-group is never consulted (root boundary only). The
equivalence test walks a cached producer → fresh consumer and asserts the delivered output is
identical to a full fresh run — the "a wrong hit is worse than no cache" guarantee at graph level.
"""

import asyncio

from shared_libs.pipelines.base import (
    ActionNode,
    FromNode,
    Group,
    OnSuccess,
    Transition,
)
from shared_libs.pipelines.engine import CacheHook

from .conftest import Cfg, Consumer, Doc, DocOut, Empty


class CountingCacheableProducer(ActionNode):
    """A cacheable producer that counts how many times it actually RAN (to prove a hit skips it)."""

    KIND = "test_cache_producer"
    NAME = "CP"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = DocOut
    CACHEABLE = True
    CACHE_VERSION = "1"

    def __init__(self, id: str, config: Cfg, text: str = "parsed") -> None:
        super().__init__(id, config)
        self._text = text
        self.run_count = 0

    async def run(self, data: Empty) -> DocOut:
        self.run_count += 1
        return DocOut(doc=Doc(text=self._text))


class InMemoryHook(CacheHook):
    """A minimal CacheHook double: an in-memory artefact store + before/after call log."""

    def __init__(self) -> None:
        self._store: dict[str, DocOut] = {}
        self.before_calls: list[str] = []
        self.after_calls: list[str] = []

    async def before(self, node_id: str, resolved_input) -> DocOut | None:
        self.before_calls.append(node_id)
        return self._store.get(node_id)

    async def after(self, node_id: str, resolved_input, output) -> None:
        self.after_calls.append(node_id)
        self._store[node_id] = output


def _producer_then_consumer(producer: ActionNode) -> Group:
    """A 2-node root graph: a cacheable producer feeding a fresh downstream consumer."""
    return Group(
        id="g",
        children=[producer, Consumer(id="c", config=Cfg())],
        transitions=[Transition(from_node_id=producer.id, to_node_id="c", condition=OnSuccess())],
        bindings={"c": {"doc": FromNode(node_id=producer.id, field_name="doc")}},
    )


def test_no_hook_runs_the_node_and_never_consults_a_cache(engine) -> None:
    """With no cache_hook the engine runs exactly as before — the node runs, nothing is consulted."""
    producer = CountingCacheableProducer(id="p", config=Cfg())
    group = _producer_then_consumer(producer)

    output, _ = asyncio.run(engine.execute(group, {}))

    assert producer.run_count == 1
    assert output.doc.text == "parsed -> C"


def test_miss_runs_the_node_then_stores_it(engine) -> None:
    """A cold cache: before is consulted (miss), the node runs, after stores its output."""
    producer = CountingCacheableProducer(id="p", config=Cfg())
    hook = InMemoryHook()
    group = _producer_then_consumer(producer)

    asyncio.run(engine.execute(group, {}, cache_hook=hook))

    assert producer.run_count == 1
    assert hook.before_calls == ["p"] and hook.after_calls == ["p"]


def test_hit_skips_the_node_run_and_serves_the_artifact(engine) -> None:
    """A warm cache HIT serves the stored artefact and SKIPS node.run entirely."""
    producer = CountingCacheableProducer(id="p", config=Cfg())
    hook = InMemoryHook()
    hook._store["p"] = DocOut(doc=Doc(text="parsed"))  # pre-seed the hit
    group = _producer_then_consumer(producer)

    output, _ = asyncio.run(engine.execute(group, {}, cache_hook=hook))

    assert producer.run_count == 0  # the node was NOT run
    assert hook.before_calls == ["p"] and hook.after_calls == []  # served, never stored
    assert output.doc.text == "parsed -> C"  # the fresh downstream still ran on the cached artefact


def test_cached_stage_plus_fresh_downstream_equals_a_full_fresh_run(engine) -> None:
    """Equivalence: a cached producer + fresh consumer yields the SAME delivery as a full fresh run."""
    # 1. A full fresh run (no cache) — the reference output.
    fresh_producer = CountingCacheableProducer(id="p", config=Cfg())
    fresh_output, _ = asyncio.run(engine.execute(_producer_then_consumer(fresh_producer), {}))

    # 2. A cold run through a real hook (miss → store), then a warm run (hit → skip) on a fresh graph.
    hook = InMemoryHook()
    cold_producer = CountingCacheableProducer(id="p", config=Cfg())
    asyncio.run(engine.execute(_producer_then_consumer(cold_producer), {}, cache_hook=hook))
    warm_producer = CountingCacheableProducer(id="p", config=Cfg())
    warm_output, _ = asyncio.run(
        engine.execute(_producer_then_consumer(warm_producer), {}, cache_hook=hook)
    )

    # 3. The warm run served the cache (producer never ran) yet delivered a byte-identical result.
    assert warm_producer.run_count == 0
    assert warm_output.doc == fresh_output.doc
    assert warm_output.model_dump() == fresh_output.model_dump()


def test_cache_seam_fires_only_at_the_root_boundary(engine) -> None:
    """A cacheable node nested inside a sub-group is NOT a stage boundary — never consulted."""
    nested = CountingCacheableProducer(id="np", config=Cfg())
    inner = Group(id="inner", children=[nested], transitions=[])
    outer = Group(id="outer", children=[inner], transitions=[])
    hook = InMemoryHook()

    asyncio.run(engine.execute(outer, {}, cache_hook=hook))

    assert nested.run_count == 1
    assert hook.before_calls == []  # the sub-group child is not a root stage boundary


def test_non_cacheable_root_node_is_never_consulted(engine) -> None:
    """A plain (non-CACHEABLE) root node is run without ever touching the cache seam."""

    class PlainProducer(ActionNode):
        KIND = "test_cache_plain"
        NAME = "PP"
        SUMMARY = "s"
        Config = Cfg
        Consumes = Empty
        Produces = DocOut

        async def run(self, data: Empty) -> DocOut:
            return DocOut(doc=Doc(text="plain"))

    hook = InMemoryHook()
    group = Group(id="g", children=[PlainProducer(id="p", config=Cfg())], transitions=[])

    asyncio.run(engine.execute(group, {}, cache_hook=hook))

    assert hook.before_calls == [] and hook.after_calls == []
