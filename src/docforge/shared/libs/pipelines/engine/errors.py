# ====== Code Summary ======
# Engine-level exceptions. EngineInvariantError marks a genuinely-unrecoverable violation of the
# engine's OWN construction invariants (e.g. a graph node whose type the engine does not support) —
# a code/build bug, not a data or configuration failure. Unlike a node/execution failure (which the
# engine RECORDS as a FAILED execution record rather than crashing the caller), an invariant
# violation is allowed to propagate out of execute() so it surfaces loudly instead of being masked
# as a recorded run failure.


class EngineInvariantError(Exception):
    """A violation of the engine's own construction invariants — surfaced loudly, never recorded.

    Raised for a state the engine can only reach through a code/build bug (e.g. a graph node whose
    type is neither an action, a foreach, nor a sub-group), as opposed to a node/execution failure
    (which the engine records as a FAILED execution record). ``FlowEngine.execute`` re-raises this
    uniformly instead of converting it to a recorded failure, so a broken engine build cannot hide.
    """


__all__ = ["EngineInvariantError"]
