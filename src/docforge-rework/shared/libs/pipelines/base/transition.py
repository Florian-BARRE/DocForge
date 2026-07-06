# ====== Code Summary ======
# Control-flow edges of the pipeline graph.
#
# A Transition is a directed edge from one node to another, gated by a Condition. The engine,
# after running a node, follows each outgoing transition whose condition holds. Sequence,
# escalation, fallback and value routing are NOT special classes — they emerge from the wiring:
#   - a plain ``Always`` edge chains two nodes (sequence),
#   - an ``OnFailure`` edge to an alternative node is a fallback / escalation,
#   - a ``ScoreBelow`` edge escalates when a node's output quality is too low,
#   - ``WhenEquals`` edges route by a value of the output (a switch — e.g. per figure class).
# Conditions are a discriminated union of Pydantic models, so they serialise into the stored
# pipeline blob and are resolved by the engine at run time. Priority when several would match:
# ScoreBelow > WhenEquals > OnSuccess/OnFailure > Always (quality escalation beats value routing).

# ====== Standard Library Imports ======
from enum import StrEnum
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ConditionKind(StrEnum):
    """The kind of a transition condition — the discriminator of the Condition union."""

    ALWAYS = "always"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    SCORE_BELOW = "score_below"
    WHEN_EQUALS = "when_equals"


class Always(BaseModel):
    """Follow the edge unconditionally, whatever the source node's outcome."""

    kind: Literal[ConditionKind.ALWAYS] = ConditionKind.ALWAYS


class OnSuccess(BaseModel):
    """Follow the edge only when the source node succeeded."""

    kind: Literal[ConditionKind.ON_SUCCESS] = ConditionKind.ON_SUCCESS


class OnFailure(BaseModel):
    """Follow the edge only when the source node failed (fallback / escalation)."""

    kind: Literal[ConditionKind.ON_FAILURE] = ConditionKind.ON_FAILURE


class ScoreBelow(BaseModel):
    """
    Follow the edge when the source node's output score is below a threshold.

    Attributes:
        threshold (float): Score under which the edge is taken — e.g. escalate to a stronger
            provider when quality is insufficient.
    """

    kind: Literal[ConditionKind.SCORE_BELOW] = ConditionKind.SCORE_BELOW
    threshold: float


class WhenEquals(BaseModel):
    """
    Follow the edge when a field of the source node's SUCCESSFUL output equals a value.

    The switch of the graph: several ``WhenEquals`` edges on the SAME field with DISTINCT values
    route each outcome to its own branch (e.g. a figure classifier's ``kind``). Values are
    compared as strings, which covers the StrEnum outputs the routing is meant for.

    Attributes:
        field (str): Field name on the source node's PRODUCES model to read.
        equals (str): The edge is taken when ``str(output.field) == equals``.
    """

    kind: Literal[ConditionKind.WHEN_EQUALS] = ConditionKind.WHEN_EQUALS
    field: str
    equals: str


# Discriminated union — Pydantic selects the right condition from the ``kind`` tag on load.
type Condition = Annotated[
    Always | OnSuccess | OnFailure | ScoreBelow | WhenEquals, Field(discriminator="kind")
]


class Transition(BaseModel):
    """
    A directed, condition-gated edge between two nodes of the same graph.

    Attributes:
        from_node_id (str): Identifier of the source node.
        to_node_id (str): Identifier of the target node, followed when the condition holds.
        condition (Condition): Gate evaluated against the source node's outcome. Defaults to
            ``OnSuccess`` — a plain edge proceeds only when the source node succeeded; use an
            explicit ``Always`` for a truly unconditional edge.
    """

    from_node_id: str
    to_node_id: str
    condition: Condition = Field(default_factory=OnSuccess)


__all__ = [
    "ConditionKind",
    "Always",
    "OnSuccess",
    "OnFailure",
    "ScoreBelow",
    "WhenEquals",
    "Condition",
    "Transition",
]
