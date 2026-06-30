# ====== Code Summary ======
# InputResolver — builds a node's typed Input from its bindings (the DATA axis). For each Input field
# it reads the bound source: a sibling node's already-collected output (FromNode), the enclosing group's
# input (FromGroupInput), or the pipeline run input (FromRunInput). This is what preserves MULTI-SOURCE
# data — a node can read the output of any prior sibling by id, not just its immediate predecessor —
# while transitions stay a pure control concern. Resolution is total: a missing required source is a
# precise ResolutionError.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .io import FromGroupInput, FromNode, FromRunInput, NodeInput, input_bindings


class ResolutionError(Exception):
    """A node's input binding could not be resolved (missing required source)."""


class InputResolver:
    """Static resolver turning a node's bindings into its concrete typed Input."""

    logger = loggerplusplus.bind(identifier="InputResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — static-only."""
        raise TypeError("InputResolver is a static-only class and cannot be instantiated.")

    @classmethod
    def resolve(
        cls,
        input_cls: type[NodeInput],
        run_input: NodeInput,
        group_input: NodeInput,
        sibling_outputs: dict,
    ) -> NodeInput:
        """
        Build a node's typed Input from its bindings.

        Args:
            input_cls (type[NodeInput]): The node's Input class (carries the bindings).
            run_input (NodeInput): The pipeline run input (source of FromRunInput).
            group_input (NodeInput): The enclosing group's input (source of FromGroupInput).
            sibling_outputs (dict): The already-collected outputs of this node's siblings, by node id.

        Returns:
            NodeInput: The validated typed Input instance.

        Raises:
            ResolutionError: When a required FromNode source has not been produced yet.
        """
        # 1. Resolve each bound field from its declared source.
        values: dict = {}
        for field, binding in input_bindings(input_cls).items():
            if isinstance(binding, FromNode):
                source = sibling_outputs.get(binding.node)
                if source is None:
                    raise ResolutionError(
                        f"{input_cls.__name__}.{field}: sibling node {binding.node!r} has not produced "
                        f"an output (check the transitions / declaration order)."
                    )
                values[field] = getattr(source, binding.field or field)
            elif isinstance(binding, FromGroupInput):
                values[field] = getattr(group_input, binding.field or field, None)
            elif isinstance(binding, FromRunInput):
                values[field] = getattr(run_input, binding.field or field, None)

        # 2. Validate against the typed Input (Pydantic enforces required / types).
        return input_cls(**values)


__all__ = ["InputResolver", "ResolutionError"]
