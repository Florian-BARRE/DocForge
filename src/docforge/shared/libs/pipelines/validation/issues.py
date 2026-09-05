# ====== Code Summary ======
# The result of validating a pipeline graph: a typed list of issues (each with a code, a location
# and a human message) and the error raised when a graph is rejected. The validator collects ALL
# issues rather than failing on the first, so a UI can show everything wrong at once.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


class ValidationCode(StrEnum):
    """
    The category of a validation issue — a stable code the UI can branch on.

    Attributes:
        NO_SINGLE_ENTRY: A group has zero or several entry nodes (needs exactly one).
        CYCLE: The transitions of a group form a cycle.
        AMBIGUOUS_ROUTING: A node has several outgoing transitions of the same condition kind, so
            routing on that outcome is ambiguous (parallel fan-out is not supported). WhenEquals
            is the exception: several are valid when they switch on ONE field with distinct values.
        WHEN_EQUALS_UNKNOWN_FIELD: A WhenEquals edge routes on a field its producer does not output.
        FOREACH_INVALID_BODY: A foreach body breaks the collection contract — its terminals must
            all be action nodes producing the same single-slot Artifact (scalar slots such as
            ``str`` are not collectable).
        UNKNOWN_NODE: A transition or binding references a node absent from the group.
        MISSING_BINDING: An action node's CONSUMES slot has no binding.
        UNKNOWN_SLOT: A binding targets an input slot the action node does not declare (a wiring
            typo the resolver would otherwise silently ignore, as it reads only declared slots).
        BINDING_NOT_UPSTREAM: A FromNode binding points at a node that is not upstream.
        UNKNOWN_FIELD: A FromNode binding reads an output field the producer does not have.
        TYPE_MISMATCH: A producer field's type is incompatible with the consuming slot's type.
        SCORE_BELOW_NOT_SCORED: A ScoreBelow edge starts from a node whose output is not scored.
        DUPLICATE_UNIQUE_NODE: A node declared UNIQUE_IN_GRAPH appears more than once in the
            whole graph (nested groups included).
    """

    NO_SINGLE_ENTRY = "no_single_entry"
    CYCLE = "cycle"
    AMBIGUOUS_ROUTING = "ambiguous_routing"
    WHEN_EQUALS_UNKNOWN_FIELD = "when_equals_unknown_field"
    FOREACH_INVALID_BODY = "foreach_invalid_body"
    UNKNOWN_NODE = "unknown_node"
    MISSING_BINDING = "missing_binding"
    UNKNOWN_SLOT = "unknown_slot"
    BINDING_NOT_UPSTREAM = "binding_not_upstream"
    UNKNOWN_FIELD = "unknown_field"
    TYPE_MISMATCH = "type_mismatch"
    SCORE_BELOW_NOT_SCORED = "score_below_not_scored"
    DUPLICATE_UNIQUE_NODE = "duplicate_unique_node"
    SWITCH_NOT_EXHAUSTIVE = "switch_not_exhaustive"


class ValidationIssue(BaseModel):
    """
    One problem found in a pipeline graph.

    Attributes:
        code (ValidationCode): The issue category.
        location (str): Where it was found (e.g. ``group 'ingest' / node 'chunk'``).
        message (str): Human-readable explanation.
    """

    code: ValidationCode
    location: str
    message: str


class GraphInvalidError(Exception):
    """Raised when a pipeline graph fails validation; carries every issue found."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        """
        Args:
            issues (list[ValidationIssue]): Every issue found in the graph.
        """
        self.issues = issues
        summary = "; ".join(issue.message for issue in issues)
        super().__init__(f"pipeline graph is invalid ({len(issues)} issue(s)): {summary}")


__all__ = ["ValidationCode", "ValidationIssue", "GraphInvalidError"]
