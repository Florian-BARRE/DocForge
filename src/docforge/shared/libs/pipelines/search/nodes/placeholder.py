# ====== Code Summary ======
# PlaceholderNode — the shared base of every SELECTABLE=False future search method. It is a fully
# concrete ActionNode (so the strict node interface is satisfied once, here) that is NEVER
# registered and NEVER wired into a graph: its run() raises. A future method subclasses it, sets its
# KIND/NAME/SUMMARY + typed described faces, and inherits both the raising body and the hidden-from-
# palette flag — so the taxonomy stays discoverable in the registry while nothing can execute it.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput


class _PlaceholderConfig(NodeConfig):
    """Knob-less base config (a concrete subclass overrides it when it has knobs)."""


class _PlaceholderConsumes(NodeInput):
    """Empty base input (a concrete subclass overrides it with typed slots)."""


class _PlaceholderProduces(NodeOutput):
    """Empty base output (a concrete subclass overrides it with typed slots)."""


class PlaceholderNode(ActionNode):
    """A registered-taxonomy-only node: hidden from the palette, never wired, run() raises."""

    KIND = "__placeholder__"
    NAME = "Placeholder"
    SUMMARY = "A future search method, registered for discoverability but not yet implemented."
    SELECTABLE = False
    Config = _PlaceholderConfig
    Consumes = _PlaceholderConsumes
    Produces = _PlaceholderProduces

    async def run(self, data: NodeInput) -> NodeOutput:
        """
        Never called — a placeholder is never wired into a built graph.

        Raises:
            NotImplementedError: Always — this method's body lands in a later phase.
        """
        raise NotImplementedError(
            f"Search method '{self.KIND}' is a placeholder (SELECTABLE=False) and has no body yet."
        )


__all__ = ["PlaceholderNode"]
