# ====== Code Summary ======
# The graphs the engine characterization runs. Each scenario is a small fixed graph of fake nodes plus
# the run arguments (run input, cache hook, resume point, trace level, deadline). ``HAPPY`` holds the
# runs that finish normally; ``BRANCHES`` the error/record-not-crash branches. A scenario is a factory
# (a fresh graph and fresh fakes each time: the cacheable producer counts its runs).

# ====== Standard Library Imports ======
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ErrorPolicy,
    ForEach,
    FromGroupInput,
    FromNode,
    FromRunInput,
    Group,
    OnFailure,
    OnSuccess,
    ScoreBelow,
    Transition,
    WhenEquals,
)
from shared_libs.pipelines.engine import ResumePoint, TraceLevel

# ====== Local Project Imports ======
from .cache_hooks import RaisingLookupHook, RaisingStoreHook, RecordingCacheHook, ServingCacheHook
from .engine_fakes import (
    CacheableProducer,
    Consumer,
    Doc,
    DocOut,
    DocsProducer,
    Failer,
    ItemEcho,
    ItemOther,
    ItemTwoSlots,
    Producer,
    Scorer,
    Sleeper,
)


@dataclass
class Scenario:
    """A graph and how to run it."""

    group: Group
    run_input: dict[str, Any] = field(default_factory=dict)
    trace_level: TraceLevel = TraceLevel.FULL
    cache_hook: Any = None
    resume: ResumePoint | None = None
    timeout_seconds: float | None = None
    with_summaries: bool = False


def _then(source: str, target: str, condition: Any = None) -> Transition:
    return Transition(from_node_id=source, to_node_id=target, condition=condition or OnSuccess())


def _doc_of(node_id: str) -> dict[str, FromNode]:
    return {"doc": FromNode(node_id=node_id, field_name="doc")}


def _chain(trace_level: TraceLevel = TraceLevel.FULL, with_summaries: bool = False) -> Scenario:
    group = Group(
        id="g",
        children=[Producer("p", "hello"), Consumer("c")],
        transitions=[_then("p", "c")],
        bindings={"c": _doc_of("p")},
    )
    return Scenario(group, trace_level=trace_level, with_summaries=with_summaries)


def foreach_group(texts: list[str], max_concurrency: int = 2) -> Group:
    body = Group(
        id="body",
        children=[ItemEcho("echo")],
        bindings={"echo": {"item": FromGroupInput(field_name="item")}},
    )
    return Group(
        id="g",
        children=[
            DocsProducer("src", texts),
            ForEach(
                "each",
                body,
                over=FromNode(node_id="src", field_name="docs"),
                item_field="item",
                max_concurrency=max_concurrency,
            ),
        ],
        transitions=[_then("src", "each")],
    )


def _foreach_over(binding: Any, run_input: dict[str, Any] | None = None) -> Scenario:
    body = Group(
        id="body",
        children=[ItemEcho("echo")],
        bindings={"echo": {"item": FromGroupInput(field_name="item")}},
    )
    group = Group(
        id="g",
        children=[
            DocsProducer("src", ["a"]),
            ForEach("each", body, over=binding, item_field="item"),
        ],
        transitions=[_then("src", "each")],
    )
    return Scenario(group, run_input=run_input or {})


def _skip_failer() -> Failer:
    failer = Failer("f")
    failer.ERROR_POLICY = ErrorPolicy.SKIP
    return failer


def _escalation(score: float) -> Scenario:
    return Scenario(
        Group(
            id="g",
            children=[Scorer("sc", score), Producer("fb", "fallback")],
            transitions=[_then("sc", "fb", ScoreBelow(threshold=0.5))],
        )
    )


def _nested() -> Scenario:
    inner = Group(
        id="inner",
        children=[Consumer("ic")],
        bindings={"ic": {"doc": FromGroupInput(field_name="doc")}},
    )
    return Scenario(
        Group(
            id="g",
            children=[Producer("seed", "seed"), inner],
            transitions=[_then("seed", "inner")],
            bindings={"inner": {"doc": FromNode(node_id="seed", field_name="doc")}},
        )
    )


def _resume() -> Scenario:
    group = Group(
        id="g",
        children=[Producer("p", "fresh"), Consumer("c")],
        transitions=[_then("p", "c")],
        bindings={"c": _doc_of("p")},
    )
    resume = ResumePoint(
        start_node_id="c",
        seeded_outputs={"p": DocOut(doc=Doc(text="seeded"))},
        downstream_ids=frozenset({"c"}),
    )
    return Scenario(group, resume=resume)


def _unbound(binding: dict[str, Any] | None, run_input: dict[str, Any] | None = None) -> Scenario:
    return Scenario(
        Group(
            id="g",
            children=[Producer("p"), Consumer("c")],
            transitions=[_then("p", "c")],
            bindings={"c": binding} if binding is not None else {},
        ),
        run_input=run_input or {},
    )


def _cacheable(hook: Any) -> Scenario:
    group = Group(
        id="g",
        children=[CacheableProducer("p", "parsed"), Consumer("c")],
        transitions=[_then("p", "c")],
        bindings={"c": _doc_of("p")},
    )
    return Scenario(group, cache_hook=hook)


def _off_contract_body() -> Scenario:
    """The first body node ends the item early on the WRONG artefact (an unmatched switch value)."""
    body = Group(
        id="body",
        children=[ItemOther("first"), ItemEcho("tail")],
        transitions=[_then("first", "tail", WhenEquals(field="other", equals="never"))],
        bindings={
            "first": {"item": FromGroupInput(field_name="item")},
            "tail": {"item": FromGroupInput(field_name="item")},
        },
    )
    group = Group(
        id="g",
        children=[
            DocsProducer("src", ["a"]),
            ForEach(
                "each", body, over=FromNode(node_id="src", field_name="docs"), item_field="item"
            ),
        ],
        transitions=[_then("src", "each")],
    )
    return Scenario(group)


def _two_slot_body() -> Scenario:
    body = Group(
        id="body",
        children=[ItemTwoSlots("two")],
        bindings={"two": {"item": FromGroupInput(field_name="item")}},
    )
    group = Group(
        id="g",
        children=[
            DocsProducer("src", ["a", "b"]),
            ForEach(
                "each", body, over=FromNode(node_id="src", field_name="docs"), item_field="item"
            ),
        ],
        transitions=[_then("src", "each")],
    )
    return Scenario(group)


def _failed_subgroup_input() -> Scenario:
    inner = Group(
        id="inner",
        children=[Consumer("ic")],
        bindings={"ic": {"doc": FromGroupInput(field_name="doc")}},
    )
    group = Group(
        id="g",
        children=[Producer("p"), inner],
        transitions=[_then("p", "inner")],
        bindings={"inner": {"doc": FromNode(node_id="ghost", field_name="doc")}},
    )
    return Scenario(group)


def _cycle() -> Scenario:
    group = Group(
        id="g",
        children=[Producer("a"), Producer("b"), Producer("c")],
        transitions=[_then("a", "b"), _then("b", "c"), _then("c", "b")],
    )
    return Scenario(group)


#: Runs that finish normally: name → scenario factory.
HAPPY: dict[str, Callable[[], Scenario]] = {
    "linear_chain": _chain,
    "linear_chain_full_trace_summaries": lambda: _chain(TraceLevel.FULL, with_summaries=True),
    "linear_chain_shape_trace_summaries": lambda: _chain(TraceLevel.SHAPE, with_summaries=True),
    "linear_chain_off_trace_summaries": lambda: _chain(TraceLevel.OFF, with_summaries=True),
    "score_below_escalates": lambda: _escalation(0.3),
    "score_above_stays": lambda: _escalation(0.9),
    "on_failure_escalates": lambda: Scenario(
        Group(
            id="g",
            children=[Failer("f"), Producer("fb", "recovered")],
            transitions=[_then("f", "fb", OnFailure())],
        )
    ),
    "skip_policy_continues": lambda: Scenario(
        Group(
            id="g",
            children=[_skip_failer(), Producer("after", "after")],
            transitions=[_then("f", "after")],
        )
    ),
    "skip_policy_terminal": lambda: Scenario(Group(id="g", children=[_skip_failer()])),
    "nested_group": _nested,
    "foreach_three_items": lambda: Scenario(foreach_group(["a", "b", "c"]), with_summaries=True),
    "foreach_empty_list": lambda: Scenario(foreach_group([])),
    "resume_from_a_stage": _resume,
    "cache_miss_stores": lambda: _cacheable(RecordingCacheHook()),
    "cache_hit_serves": lambda: _cacheable(ServingCacheHook(DocOut(doc=Doc(text="cached")))),
}

#: The error / record-not-crash branches: name → scenario factory.
BRANCHES: dict[str, Callable[[], Scenario]] = {
    "node_failure_with_fail_policy": lambda: Scenario(
        Group(
            id="g",
            children=[Failer("f"), Producer("never")],
            transitions=[_then("f", "never")],
        )
    ),
    "input_slot_without_binding": lambda: _unbound(None),
    "input_binds_a_node_that_never_ran": lambda: _unbound(_doc_of("ghost")),
    "input_binds_a_missing_output_field": lambda: _unbound(
        {"doc": FromNode(node_id="p", field_name="nope")}
    ),
    "input_binds_a_missing_run_input_field": lambda: _unbound(
        {"doc": FromRunInput(field_name="absent")}
    ),
    "input_type_violation": lambda: Scenario(
        Group(
            id="g",
            children=[DocsProducer("src", ["a"]), Consumer("c")],
            transitions=[_then("src", "c")],
            bindings={"c": {"doc": FromNode(node_id="src", field_name="note")}},
        )
    ),
    "cache_lookup_raises": lambda: _cacheable(RaisingLookupHook()),
    "cache_store_raises": lambda: _cacheable(RaisingStoreHook()),
    "foreach_over_run_input_missing": lambda: _foreach_over(FromRunInput(field_name="items")),
    "foreach_over_not_a_list": lambda: _foreach_over(FromNode(node_id="src", field_name="note")),
    "foreach_body_two_slot_terminal": _two_slot_body,
    "foreach_item_fails": lambda: Scenario(foreach_group(["a", "boom", "c", "boom"], 1)),
    "foreach_item_ends_off_contract": _off_contract_body,
    "subgroup_input_resolution_fails": _failed_subgroup_input,
    "cycle_guard": _cycle,
    "two_entry_nodes": lambda: Scenario(Group(id="g", children=[Producer("a"), Producer("b")])),
    "dangling_transition_target": lambda: Scenario(
        Group(id="g", children=[Producer("a")], transitions=[_then("a", "ghost")])
    ),
    "resume_at_unknown_node": lambda: Scenario(
        Group(id="g", children=[Producer("a")]), resume=ResumePoint(start_node_id="ghost")
    ),
    "run_timeout": lambda: Scenario(
        Group(id="g", children=[Sleeper("slow")]), timeout_seconds=0.05
    ),
}
