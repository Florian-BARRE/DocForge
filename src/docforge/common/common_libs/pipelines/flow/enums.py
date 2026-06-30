# ====== Code Summary ======
# The fixed vocabulary of the flow engine — every choice is an enum (no free-form DSL), so a pipeline
# is fully described by data the frontend can render and the builder can re-instantiate. NodeKind is
# the two kinds of node (an elementary action, or a group of nodes wired by transitions). Condition is
# the fixed set of transition conditions: ``always`` (sequential — proceed on success), ``score_below``
# (escalate to an alternative when the result quality is too low), ``on_failure`` (fall back on error).

# ====== Standard Library Imports ======
from enum import StrEnum


class NodeKind(StrEnum):
    """The two kinds of node in the flow tree."""

    ACTION = "action"  # an elementary unit of work (docling parse, an OCR call, content-address)
    GROUP = "group"  # a node containing child nodes wired by transitions (a stage / the pipeline)


class Condition(StrEnum):
    """The fixed set of conditions a transition can carry (when the edge fires)."""

    ALWAYS = "always"  # unconditional: take this edge whenever the source node succeeds (sequencing)
    SCORE_BELOW = "score_below"  # take this edge when the source result's score < threshold (escalate)
    ON_FAILURE = "on_failure"  # take this edge when the source node failed (fallback)


__all__ = ["NodeKind", "Condition"]
