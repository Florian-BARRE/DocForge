# ====== Code Summary ======
# The reusable capability-chain fragment builder — the one place the "provider chain" topology
# lives. A chain is an ordered list of provider steps sharing a single consumed face: each step
# escalates to the next on low quality (score_below) and falls through on failure, and the chain's
# output reads whichever step actually answered. A single-provider chain is just a 1-step chain
# (its output is a plain FromNode, byte-identical to a lone provider node). The builder emits ONLY
# the intra-chain topology (nodes, escalation edges, per-step bindings, convergence output); the
# call-site owns the entry edge into the head and any terminal it wants to hang off the exits.
#
# Layering: this module sits in build/ and imports ONLY from base + build/blob so it can be reused
# by both the enrich body and (later) the ingest assembler — it MUST NOT import from ingest/.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    Binding,
    FromFirst,
    FromNode,
    OnFailure,
    ScoreBelow,
    Transition,
)
from shared_libs.pipelines.build.blob import ActionNodeBlob


@dataclass(frozen=True)
class ChainStepSpec:
    """
    One provider step of a chain — the build-level value the fragment builder consumes.

    Deliberately defined HERE (not imported from the stage layer) so the builder stays free of any
    ingest/ dependency; the stage layer maps its own ``ChainStep`` onto this.

    Attributes:
        kind (str): Registry kind within the chain's family (e.g. ``rapidocr``, ``mistral``).
        config (dict): The provider's config (endpoint, key, prompt…).
        score_below (float | None): Escalate to the next step when this step's score is below the
            threshold; ``None`` means fall through on failure only (or the step is terminal).
    """

    kind: str
    config: dict[str, Any] = field(default_factory=dict)
    score_below: float | None = None


@dataclass(frozen=True)
class ChainFragment:
    """
    The assembled fragment of a capability chain — pure topology, ready to splice at a call-site.

    Attributes:
        nodes (list[ActionNodeBlob]): The provider step nodes, in order (cheap → robust).
        transitions (list[Transition]): The intra-chain escalation edges (score_below + on_failure).
        bindings (dict[str, dict[str, Binding]]): The consumed face of every step, keyed by step id.
        heads (list[str]): The single entry point — ``[steps[0].id]`` — an edge must route here.
        exits (list[str]): Every step id; each is a success exit (any step may be the one that ran).
        output (Binding): The chain's result binding — a plain ``FromNode`` for a 1-step chain, a
            best-first ``FromFirst`` over the steps otherwise.
        output_field (str): The producer field name the output binding reads.
        dropped_score_below (bool): True when a step carried a ``score_below`` that was dropped
            because the family is not scored — the caller/compiler may surface this as a notice.
    """

    nodes: list[ActionNodeBlob]
    transitions: list[Transition]
    bindings: dict[str, dict[str, Binding]]
    heads: list[str]
    exits: list[str]
    output: Binding
    output_field: str
    dropped_score_below: bool


class ChainFragmentBuilder:
    """Static builder turning an ordered list of provider steps into a spliceable chain fragment."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChainFragmentBuilder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(
        cls,
        *,
        prefix: str,
        family: str,
        steps: list[ChainStepSpec],
        step_inputs: dict[str, Binding],
        output_field: str,
        scored: bool,
    ) -> ChainFragment:
        """
        Assemble the chain fragment from its steps and the face every step consumes.

        Args:
            prefix (str): Id prefix for the step nodes (``f"{prefix}_{i}"``).
            family (str): Registry family every step draws its kind from.
            steps (list[ChainStepSpec]): The ordered provider steps (cheap → robust).
            step_inputs (dict[str, Binding]): The consumed face, bound identically to every step.
            output_field (str): The producer field the chain's output reads.
            scored (bool): Whether the family's PRODUCES is score-bearing — gates ``score_below``
                edges (never emitted for a non-scored family, which the validator would reject).

        Returns:
            ChainFragment: The pure fragment (nodes, escalation edges, bindings, output, flags).

        Raises:
            ValueError: When ``steps`` is empty — a chain needs at least one provider.
        """
        # 1. Guard: a chain is at least one provider.
        if not steps:
            raise ValueError(f"chain fragment '{prefix}': at least one step is required.")

        # 2. The step nodes, each reading the SAME consumed face.
        step_ids = [f"{prefix}_{index}" for index in range(len(steps))]
        nodes = [
            ActionNodeBlob(id=step_id, family=family, kind=step.kind, config=dict(step.config))
            for step_id, step in zip(step_ids, steps, strict=True)
        ]
        bindings = {step_id: dict(step_inputs) for step_id in step_ids}

        # 3. The intra-chain escalation edges and the convergence output.
        transitions, dropped = cls.__escalation(step_ids, steps, scored)
        output = cls.__output(step_ids, output_field)

        return ChainFragment(
            nodes=nodes,
            transitions=transitions,
            bindings=bindings,
            heads=[step_ids[0]],
            exits=list(step_ids),
            output=output,
            output_field=output_field,
            dropped_score_below=dropped,
        )

    @classmethod
    def __escalation(
        cls, step_ids: list[str], steps: list[ChainStepSpec], scored: bool
    ) -> tuple[list[Transition], bool]:
        """
        Build the step→step edges: a ScoreBelow escalation (when scored) plus an OnFailure fall-through.

        Args:
            step_ids (list[str]): The step node ids, in order.
            steps (list[ChainStepSpec]): The steps aligned with ``step_ids``.
            scored (bool): Whether ScoreBelow edges are allowed for this family.

        Returns:
            tuple[list[Transition], bool]: The escalation edges and whether a score_below was dropped.
        """
        transitions: list[Transition] = []
        dropped = False
        # The CURRENT step's score_below drives escalation to the NEXT step; the last step is terminal.
        for current_id, next_id, step in zip(step_ids, step_ids[1:], steps, strict=False):
            if step.score_below is not None:
                if scored:
                    transitions.append(
                        Transition(
                            from_node_id=current_id,
                            to_node_id=next_id,
                            condition=ScoreBelow(threshold=step.score_below),
                        )
                    )
                else:
                    dropped = True
            transitions.append(
                Transition(from_node_id=current_id, to_node_id=next_id, condition=OnFailure())
            )
        return transitions, dropped

    @classmethod
    def __output(cls, step_ids: list[str], output_field: str) -> Binding:
        """
        Build the chain's output binding: a plain FromNode for one step, a best-first FromFirst else.

        Args:
            step_ids (list[str]): The step node ids, in order.
            output_field (str): The producer field the binding reads.

        Returns:
            Binding: ``FromNode`` (1 step) or ``FromFirst`` over the steps, best (last) first.
        """
        if len(step_ids) == 1:
            return FromNode(node_id=step_ids[0], field_name=output_field)
        return FromFirst(
            candidates=[
                FromNode(node_id=step_id, field_name=output_field) for step_id in reversed(step_ids)
            ]
        )


__all__ = ["ChainStepSpec", "ChainFragment", "ChainFragmentBuilder"]
