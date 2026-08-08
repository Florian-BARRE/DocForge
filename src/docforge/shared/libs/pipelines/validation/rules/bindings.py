# ====== Code Summary ======
# The binding rules: given a single FromNode binding (or a foreach's 'over' / 'items'), check that
# the producer exists, sits UPSTREAM of the consumer, exposes the read field, and produces a type
# shape-compatible with the consuming slot. These are the lowest-level checks — the "how to judge one
# binding" — reused by the per-child slot coverage (child.py) and by foreach's inline over binding.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    ForEach,
    FromNode,
    SlotTypes,
)

# ====== Local Project Imports ======
from ..issues import ValidationCode
from .collector import IssueCollector


class BindingRules:
    """Static-only checks for a single binding: existence, upstream position, field, and type."""

    logger = loggerplusplus.bind(identifier="BindingRules")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BindingRules is a static-only class and cannot be instantiated.")

    @classmethod
    def check_from_node(
        cls,
        location: str,
        consumer_id: str,
        slot_name: str,
        consumer_type: type | None,
        binding: FromNode,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        collector: IssueCollector,
    ) -> None:
        """Validate a single FromNode binding: producer exists, is upstream, field + type match."""
        # 1. The producer must exist in the group.
        producer = children.get(binding.node_id)
        if producer is None:
            collector.record(
                ValidationCode.UNKNOWN_NODE,
                location,
                f"slot '{slot_name}' binds to unknown node '{binding.node_id}'",
            )
            return

        # 2. The producer must be upstream (skip when cyclic — the order is undefined).
        if not has_cycle and binding.node_id not in ancestors.get(consumer_id, set()):
            collector.record(
                ValidationCode.BINDING_NOT_UPSTREAM,
                location,
                f"slot '{slot_name}' binds to '{binding.node_id}', which is not upstream of it",
            )

        # 3. A foreach producer exposes exactly one field: 'items', typed by its body's terminals.
        if isinstance(producer, ForEach):
            cls.check_foreach_field(
                location, slot_name, consumer_type, binding, producer, collector
            )
            return

        # 4. Field + type checks apply only to action producers (a group has no typed Produces).
        if not isinstance(producer, ActionNode):
            return
        produces_fields = producer.Produces.model_fields
        if binding.field_name not in produces_fields:
            collector.record(
                ValidationCode.UNKNOWN_FIELD,
                location,
                f"producer '{binding.node_id}' has no output field '{binding.field_name}'",
            )
            return
        if consumer_type is None:
            return
        producer_type = produces_fields[binding.field_name].annotation
        # Shape-aware compatibility: plain↔plain and list↔list (by element subclass); a shape
        # mismatch (a list into a single slot, or the reverse) is always an error.
        producer_element, producer_is_list = SlotTypes.element(producer_type)
        consumer_element, consumer_is_list = SlotTypes.element(consumer_type)
        if producer_element is None or consumer_element is None:
            return  # an unreadable annotation cannot be judged here (enforced at definition)
        if producer_is_list != consumer_is_list or not issubclass(
            producer_element, consumer_element
        ):
            collector.record(
                ValidationCode.TYPE_MISMATCH,
                location,
                f"slot '{slot_name}' expects '{SlotTypes.label(consumer_type)}' but "
                f"'{binding.node_id}.{binding.field_name}' produces "
                f"'{SlotTypes.label(producer_type)}'",
            )

    @classmethod
    def check_foreach_field(
        cls,
        location: str,
        slot_name: str,
        consumer_type: type | None,
        binding: FromNode,
        producer: ForEach,
        collector: IssueCollector,
    ) -> None:
        """Validate a binding that reads a foreach's output: the field and the collected type."""
        # 1. The only output field a foreach exposes is the collected 'items'.
        if binding.field_name != "items":
            collector.record(
                ValidationCode.UNKNOWN_FIELD,
                location,
                f"foreach '{binding.node_id}' only outputs 'items', not '{binding.field_name}'",
            )
            return
        # 2. Type check: the consumer must take a list of the body's terminal artefact. A broken
        #    body (item_type None) is reported by the foreach's own body check, not here.
        item_type = producer.item_type()
        if consumer_type is None or item_type is None:
            return
        consumer_element, consumer_is_list = SlotTypes.element(consumer_type)
        if consumer_element is None:
            return
        if not consumer_is_list or not issubclass(item_type, consumer_element):
            collector.record(
                ValidationCode.TYPE_MISMATCH,
                location,
                f"slot '{slot_name}' expects '{SlotTypes.label(consumer_type)}' but foreach "
                f"'{binding.node_id}' produces 'list[{item_type.__name__}]'",
            )

    @classmethod
    def check_foreach_over(
        cls,
        location: str,
        child: ForEach,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        collector: IssueCollector,
    ) -> None:
        """Validate a foreach's 'over' binding: standard FromNode checks plus the list shape."""
        if not isinstance(child.over, FromNode):
            return  # run/group inputs are dynamic — checked at run time
        # 1. Producer exists, is upstream, field exists (the standard binding checks).
        cls.check_from_node(
            location, child.id, "over", None, child.over, children, ancestors, has_cycle, collector
        )
        # 2. The bound field must be a list — the loop needs something to iterate.
        producer = children.get(child.over.node_id)
        if not isinstance(producer, ActionNode):
            return
        field_info = producer.Produces.model_fields.get(child.over.field_name)
        if field_info is None:
            return  # already reported as unknown_field above
        element, is_list = SlotTypes.element(field_info.annotation)
        if element is not None and not is_list:
            collector.record(
                ValidationCode.TYPE_MISMATCH,
                location,
                f"'over' must bind a list field, but '{child.over.node_id}."
                f"{child.over.field_name}' produces '{SlotTypes.label(field_info.annotation)}'",
            )


__all__ = ["BindingRules"]
