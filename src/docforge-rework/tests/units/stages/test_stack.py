"""SetStack: 0..3 contextualize methods, reordering, empty stack disables the stage."""

import itertools

import pytest

from shared_libs.pipelines.base import FromNode
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import SetStack, StackMethod, StateReader

_METHODS = ["doc_meta", "breadcrumb", "sliding"]
_ALL_PERMUTATIONS = list(itertools.chain.from_iterable(
    itertools.permutations(_METHODS, r) for r in range(0, len(_METHODS) + 1)
))


@pytest.mark.parametrize("combo", _ALL_PERMUTATIONS, ids=lambda c: "-".join(c) or "empty")
def test_every_stack_permutation_validates_and_orders_correctly(compiler, builder, validator, combo) -> None:
    default = IngestPipeline.default_blob()
    steps = [StackMethod(kind=kind, config={}) for kind in combo]
    restacked, notices = compiler.apply(default, SetStack(stage="contextualize", steps=steps))
    assert validator.validate(builder.build(restacked)) == [], (combo, notices)

    read_back = StateReader.read(restacked)
    assert [m.kind for m in read_back.stack] == list(combo)

    if not combo:
        assert notices  # emptying the stack is flagged
        return

    # The chain order: chunk -> first method -> second -> ... in application order.
    ctx_ids = [n.id for n in restacked.nodes if getattr(n, "family", None) == "contextualize"]
    assert len(ctx_ids) == len(combo)
    assert restacked.bindings[ctx_ids[0]]["chunks"] == FromNode(node_id="chunk", field_name="chunks")
    for previous, current in zip(ctx_ids, ctx_ids[1:], strict=False):
        assert restacked.bindings[current]["chunks"] == FromNode(node_id=previous, field_name="chunks")


def test_repeatable_kind_twice_in_the_stack_gets_distinct_ids(compiler, builder, validator) -> None:
    """A kind NOT flagged UNIQUE_IN_GRAPH (llm_context) may appear twice; ids stay distinct."""
    from shared_libs.pipelines.registry import NodeRegistry

    assert NodeRegistry.get("contextualize", "llm").describe().unique_in_graph is False
    default = IngestPipeline.default_blob()
    restacked, notices = compiler.apply(
        default,
        SetStack(stage="contextualize", steps=[
            StackMethod(kind="llm", config={"base_url": "http://x", "model": "m", "document_scope": "section"}),
            StackMethod(kind="llm", config={"base_url": "http://x", "model": "m", "document_scope": "full"}),
        ]),
    )
    assert validator.validate(builder.build(restacked)) == [], notices
    ctx_ids = [n.id for n in restacked.nodes if getattr(n, "family", None) == "contextualize"]
    assert len(ctx_ids) == 2 and len(set(ctx_ids)) == 2


def test_empty_stack_disables_the_contextualize_stage(compiler) -> None:
    default = IngestPipeline.default_blob()
    emptied, notices = compiler.apply(default, SetStack(stage="contextualize", steps=[]))
    assert "contextualize stack emptied" in " ".join(notices)
    read_back = StateReader.read(emptied)
    assert read_back.stack == []
