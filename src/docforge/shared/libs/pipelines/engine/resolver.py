# ====== Code Summary ======
# Resolves a node's typed input (its Consumes instance) from the graph wiring: each declared input
# slot is filled from its Binding — a field of the run input (FromRunInput), of the enclosing
# group's input (FromGroupInput), a specific upstream node's output (FromNode), or the first of
# several alternative producers that actually ran (FromFirst — the join of branched graphs). Any
# miss raises a precise ResolutionError so a broken wiring fails loudly, never silently.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    Binding,
    FromFirst,
    FromGroupInput,
    FromNode,
    FromRunInput,
    NodeInput,
    NodeOutput,
)


class ResolutionError(Exception):
    """Raised when a node input slot cannot be resolved from the available data."""


class InputResolver:
    """Static helper building a node's Consumes instance from its bindings and the available data."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("InputResolver is a static-only class and cannot be instantiated.")

    @staticmethod
    def __read(source: dict[str, Any], field_name: str, label: str) -> Any:
        """Read a field from a direct source dict, raising a precise error on a miss."""
        if field_name not in source:
            raise ResolutionError(f"{label} has no field '{field_name}'.")
        return source[field_name]

    @classmethod
    def __resolve_one(
        cls,
        slot_name: str,
        binding: Binding,
        run_input: dict[str, Any],
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> Any:
        """Resolve a single slot from its binding."""
        # 1. Direct sources: the run input or the enclosing group's input.
        if isinstance(binding, FromRunInput):
            return cls.__read(run_input, binding.field_name, "run input")
        if isinstance(binding, FromGroupInput):
            return cls.__read(group_input, binding.field_name, "group input")

        # 2. Sibling source: a specific upstream node's output field.
        if isinstance(binding, FromNode):
            output = node_outputs.get(binding.node_id)
            if output is None:
                raise ResolutionError(
                    f"Slot '{slot_name}' binds to node '{binding.node_id}', "
                    f"which has produced no output (not run yet or failed)."
                )
            if not hasattr(output, binding.field_name):
                raise ResolutionError(
                    f"Node '{binding.node_id}' output has no field '{binding.field_name}'."
                )
            return getattr(output, binding.field_name)

        # 3. Convergence join: the first candidate that actually produced (branches are
        #    exclusive, so exactly one alternative ran — candidates are listed best-first).
        if isinstance(binding, FromFirst):
            for candidate in binding.candidates:
                output = node_outputs.get(candidate.node_id)
                if output is not None and hasattr(output, candidate.field_name):
                    return getattr(output, candidate.field_name)
            raise ResolutionError(
                f"Slot '{slot_name}': none of the FromFirst candidates "
                f"({', '.join(c.node_id for c in binding.candidates)}) produced an output."
            )

        # 4. Unreachable while Binding stays a closed union — guard anyway.
        raise ResolutionError(f"Slot '{slot_name}' has an unknown binding type.")

    @classmethod
    def resolve(
        cls,
        consumes_model: type[NodeInput],
        bindings: dict[str, Binding],
        run_input: dict[str, Any],
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> NodeInput:
        """
        Build a node's Consumes instance by resolving every declared input slot.

        Args:
            consumes_model (type[NodeInput]): The node's CONSUMES class.
            bindings (dict[str, Binding]): Slot name → its Binding for this node.
            run_input (dict[str, Any]): The pipeline run input.
            group_input (dict[str, Any]): The enclosing group's input.
            node_outputs (dict[str, NodeOutput]): Outputs of already-run sibling nodes.

        Returns:
            NodeInput: The populated Consumes instance.

        Raises:
            ResolutionError: If a slot has no binding or the binding cannot be satisfied.
        """
        # 1. Fill every declared slot from its binding; an OPTIONAL slot (field with a
        #    default) may stay unbound — its default applies, so variant pipelines can
        #    simply not produce it (e.g. a bundle without metagen or embeddings).
        values: dict[str, Any] = {}
        for slot_name, field_info in consumes_model.model_fields.items():
            binding = bindings.get(slot_name)
            if binding is None:
                if field_info.is_required():
                    raise ResolutionError(f"Input slot '{slot_name}' has no binding.")
                continue
            values[slot_name] = cls.__resolve_one(
                slot_name, binding, run_input, group_input, node_outputs
            )

        # 2. Build the typed Consumes model (Pydantic validates the resolved values).
        return consumes_model(**values)

    @classmethod
    def resolve_mapping(
        cls,
        bindings: dict[str, Binding],
        run_input: dict[str, Any],
        group_input: dict[str, Any],
        node_outputs: dict[str, NodeOutput],
    ) -> dict[str, Any]:
        """
        Resolve a set of bindings into a plain value dict.

        Used for a sub-group's input: a group has no typed Consumes model, so its input is a
        dynamic dict its children then read via ``FromGroupInput``.

        Args:
            bindings (dict[str, Binding]): Target field name → its Binding.
            run_input (dict[str, Any]): The pipeline run input.
            group_input (dict[str, Any]): The enclosing group's input.
            node_outputs (dict[str, NodeOutput]): Outputs of already-run sibling nodes.

        Returns:
            dict[str, Any]: The resolved field values.

        Raises:
            ResolutionError: If any binding cannot be satisfied.
        """
        return {
            field_name: cls.__resolve_one(field_name, binding, run_input, group_input, node_outputs)
            for field_name, binding in bindings.items()
        }


__all__ = ["InputResolver", "ResolutionError"]
