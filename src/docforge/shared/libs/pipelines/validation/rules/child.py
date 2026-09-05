# ====== Code Summary ======
# The per-child binding coverage rule: for one child of a group, iterate the bindings it should carry
# and hand each to the low-level BindingRules. An action node must bind every required CONSUMES slot
# (a FromFirst join is checked candidate by candidate); a foreach child is validated through its inline
# 'over' binding; a sub-group's dynamic bindings can only be checked for upstream + producer field.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    AbstractNode,
    ActionNode,
    ForEach,
    FromFirst,
    FromNode,
    Group,
)

# ====== Local Project Imports ======
from ..issues import ValidationCode
from .bindings import BindingRules
from .collector import IssueCollector


class ChildBindingRules:
    """Static-only rule validating one child's bindings — full slot coverage plus FromNode checks."""

    logger = loggerplusplus.bind(identifier="ChildBindingRules")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChildBindingRules is a static-only class and cannot be instantiated.")

    @classmethod
    def validate_child(
        cls,
        group: Group,
        child: AbstractNode,
        children: dict[str, AbstractNode],
        ancestors: dict[str, set[str]],
        has_cycle: bool,
        collector: IssueCollector,
    ) -> None:
        """Validate one child's bindings — full slot coverage for action nodes, FromNode for groups."""
        location = f"group '{group.id}' / node '{child.id}'"
        node_bindings = group.bindings.get(child.id, {})

        # 0. ForEach child: its single input is the inline 'over' binding.
        if isinstance(child, ForEach):
            BindingRules.check_foreach_over(
                location, child, children, ancestors, has_cycle, collector
            )
            return

        # 1. Action node: every declared CONSUMES slot must be bound; a FromFirst join is checked
        #    candidate by candidate (each one like a plain FromNode).
        if isinstance(child, ActionNode):
            # 1a. A binding to a slot the node does NOT declare is a wiring typo. The resolver reads
            #     only declared slots, so it would silently ignore such a binding — flag it here so
            #     it fails fast at build like every other structural error (unlike a GROUP child,
            #     whose input is a dynamic dict where any field name is legitimate).
            declared_slots = set(child.Consumes.model_fields)
            for bound_slot in node_bindings:
                if bound_slot not in declared_slots:
                    collector.record(
                        ValidationCode.UNKNOWN_SLOT,
                        location,
                        f"binding to unknown input slot '{bound_slot}' "
                        f"(node declares: {sorted(declared_slots)})",
                    )
            for slot_name, field_info in child.Consumes.model_fields.items():
                binding = node_bindings.get(slot_name)
                if binding is None:
                    # An optional slot (field with a default) may stay unbound — mirror of
                    # the resolver's rule, so validation and execution always agree.
                    if field_info.is_required():
                        collector.record(
                            ValidationCode.MISSING_BINDING,
                            location,
                            f"required input slot '{slot_name}' has no binding",
                        )
                    continue
                if isinstance(binding, FromNode):
                    BindingRules.check_from_node(
                        location,
                        child.id,
                        slot_name,
                        field_info.annotation,
                        binding,
                        children,
                        ancestors,
                        has_cycle,
                        collector,
                    )
                elif isinstance(binding, FromFirst):
                    for candidate in binding.candidates:
                        BindingRules.check_from_node(
                            location,
                            child.id,
                            slot_name,
                            field_info.annotation,
                            candidate,
                            children,
                            ancestors,
                            has_cycle,
                            collector,
                        )
            return

        # 2. Group child: input is a dynamic dict, so only its FromNode bindings can be checked
        #    (upstream + producer field), without a consuming slot type.
        for field_name, binding in node_bindings.items():
            if isinstance(binding, FromNode):
                BindingRules.check_from_node(
                    location,
                    child.id,
                    field_name,
                    None,
                    binding,
                    children,
                    ancestors,
                    has_cycle,
                    collector,
                )
            elif isinstance(binding, FromFirst):
                for candidate in binding.candidates:
                    BindingRules.check_from_node(
                        location,
                        child.id,
                        field_name,
                        None,
                        candidate,
                        children,
                        ancestors,
                        has_cycle,
                        collector,
                    )


__all__ = ["ChildBindingRules"]
