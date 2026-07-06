# ====== Code Summary ======
# Per-node error policy: the node's intrinsic stance when its own execution fails. This is the
# vertical recovery primitive — it composes later with the horizontal control-flow transitions
# (e.g. `on_failure` edges). The policy says what the engine does with the failure itself; a
# transition says where the graph goes next.

# ====== Standard Library Imports ======
from enum import StrEnum


class ErrorPolicy(StrEnum):
    """
    How the engine treats a failure raised by a node that has no OnFailure recovery edge.

    Attributes:
        FAIL: Propagate the failure — the group fails. The safest default.
        SKIP: Skip the failed node and continue the graph via its success-path edge. Its output
            is not produced, so a downstream node that strictly needs it will fail to resolve.
    """

    FAIL = "fail"
    SKIP = "skip"


__all__ = ["ErrorPolicy"]
