# ====== Code Summary ======
# Flattens a built pipeline graph into plain data for a golden: every node (id, node type, kind, error
# policy, the names of its Consumes / Produces slots), every transition (source, target, condition) and
# every data binding, recursively through sub-groups and ForEach bodies. Node configs are left out on
# purpose (the default-blob golden in tests/units/stages already pins them): this captures TOPOLOGY.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import AbstractNode, ActionNode, ForEach, Group


class GraphOutline:
    """Static-only helper: a built graph → a JSON-friendly outline of its structure."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("GraphOutline is a static-only class and cannot be instantiated.")

    @classmethod
    def node(cls, node: AbstractNode) -> dict[str, Any]:
        """Outline one node; a Group lists its children/transitions/bindings, a ForEach its loop + body."""
        outline: dict[str, Any] = {
            "id": node.id,
            "node_type": node.NODE_TYPE.value,
            "kind": node.KIND,
            "error_policy": node.ERROR_POLICY.value,
        }
        if isinstance(node, ActionNode):
            outline["consumes"] = list(node.Consumes.model_fields)
            outline["produces"] = list(node.Produces.model_fields)
        elif isinstance(node, ForEach):
            outline["over"] = node.over.model_dump(mode="json")
            outline["item_field"] = node.item_field
            outline["max_concurrency"] = node.max_concurrency
            outline["body"] = cls.node(node.body)
        elif isinstance(node, Group):
            outline["children"] = [cls.node(child) for child in node.children]
            outline["transitions"] = [
                {
                    "from": transition.from_node_id,
                    "to": transition.to_node_id,
                    "condition": transition.condition.model_dump(mode="json"),
                }
                for transition in node.transitions
            ]
            outline["bindings"] = {
                node_id: {slot: binding.model_dump(mode="json") for slot, binding in slots.items()}
                for node_id, slots in node.bindings.items()
            }
        return outline
