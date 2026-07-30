"""ChainFragmentBuilder in isolation: the reusable provider-chain topology.

Proves the four load-bearing shapes the enrich body (and later the ingest assembler) rely on:
  a. a 1-step chain is byte-identical to a lone provider — one node, a plain FromNode output, no
     escalation edges;
  b. a 2-step SCORED chain escalates on ScoreBelow + falls through on OnFailure, and converges
     best-first (FromFirst([step1, step0]));
  c. a 2-step NON-scored chain emits ONLY OnFailure, drops any score_below and flags the drop;
  d. the consumed face is bound identically to every step.
"""

import pytest

from shared_libs.pipelines.base import FromFirst, FromNode
from shared_libs.pipelines.build import ChainFragmentBuilder, ChainStepSpec

_INPUTS = {"figure": FromNode(node_id="classify", field_name="figure")}


def _conditions(fragment) -> list[str]:
    return [t.condition.kind.value for t in fragment.transitions]


def test_single_step_is_a_lone_provider() -> None:
    """N=1: one node, a plain FromNode output, no transitions — the single-provider shape."""
    fragment = ChainFragmentBuilder.build(
        prefix="ocr",
        family="ocr",
        steps=[ChainStepSpec(kind="rapidocr", config={})],
        step_inputs=_INPUTS,
        output_field="figure",
        scored=True,
    )
    assert [n.id for n in fragment.nodes] == ["ocr_0"]
    assert fragment.transitions == []
    assert fragment.heads == ["ocr_0"]
    assert fragment.exits == ["ocr_0"]
    assert fragment.output == FromNode(node_id="ocr_0", field_name="figure")
    assert fragment.dropped_score_below is False


def test_two_step_scored_escalates_and_converges_best_first() -> None:
    """N=2 scored: ScoreBelow + OnFailure between steps, FromFirst([step1, step0]) output."""
    fragment = ChainFragmentBuilder.build(
        prefix="ocr",
        family="ocr",
        steps=[
            ChainStepSpec(kind="rapidocr", config={}, score_below=0.4),
            ChainStepSpec(kind="mistral", config={"api_key": "x"}),
        ],
        step_inputs=_INPUTS,
        output_field="figure",
        scored=True,
    )
    assert [n.id for n in fragment.nodes] == ["ocr_0", "ocr_1"]
    # The escalation pair: ScoreBelow first, then the OnFailure fall-through — both step_0 -> step_1.
    assert _conditions(fragment) == ["score_below", "on_failure"]
    assert all(t.from_node_id == "ocr_0" and t.to_node_id == "ocr_1" for t in fragment.transitions)
    assert fragment.transitions[0].condition.threshold == 0.4
    assert isinstance(fragment.output, FromFirst)
    assert [c.node_id for c in fragment.output.candidates] == ["ocr_1", "ocr_0"]
    # Every convergence candidate reads the SAME produced slot (output_field), not the step id.
    assert all(c.field_name == "figure" for c in fragment.output.candidates)
    assert fragment.dropped_score_below is False


def test_empty_steps_is_rejected() -> None:
    """A chain needs at least one provider — an empty step list is a build error, not a no-op."""
    with pytest.raises(ValueError):
        ChainFragmentBuilder.build(
            prefix="ocr",
            family="ocr",
            steps=[],
            step_inputs=_INPUTS,
            output_field="figure",
            scored=True,
        )


def test_two_step_non_scored_drops_score_below_and_flags_it() -> None:
    """N=2 non-scored: ONLY OnFailure survives; the score_below is dropped and the flag is set."""
    fragment = ChainFragmentBuilder.build(
        prefix="llm",
        family="llm",
        steps=[
            ChainStepSpec(kind="openai_compatible", config={}, score_below=0.5),
            ChainStepSpec(kind="mistral", config={}),
        ],
        step_inputs=_INPUTS,
        output_field="completion",
        scored=False,
    )
    assert _conditions(fragment) == ["on_failure"]
    assert fragment.transitions[0].from_node_id == "llm_0"
    assert fragment.transitions[0].to_node_id == "llm_1"
    assert fragment.dropped_score_below is True


def test_step_inputs_are_bound_identically_on_every_step() -> None:
    """The consumed face appears on each step's bindings, keyed by step id."""
    fragment = ChainFragmentBuilder.build(
        prefix="ocr",
        family="ocr",
        steps=[ChainStepSpec(kind="rapidocr"), ChainStepSpec(kind="mistral")],
        step_inputs=_INPUTS,
        output_field="figure",
        scored=True,
    )
    assert set(fragment.bindings) == {"ocr_0", "ocr_1"}
    for step_id in ("ocr_0", "ocr_1"):
        assert fragment.bindings[step_id] == _INPUTS
