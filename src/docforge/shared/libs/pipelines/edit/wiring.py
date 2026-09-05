# ====== Code Summary ======
# Auto-wiring for a freshly added node: for each of its CONSUMES slots, find the sound sources in
# the same container and bind the slot ONLY when exactly one exists — ambiguity stays a manual
# choice, exactly like the client. "Sound" is the validator's own notion, reused (never re-derived
# subtly differently): a source is a sibling that is genuinely UPSTREAM after the new chaining edge
# (GraphTopology.ancestors) and whose produced artefact is type-compatible with the slot
# (SlotTypes element subclass + matching list shape). Types are read straight off the registered
# node classes' Produces/Consumes faces — no instances built, so incomplete configs never block.
#
# Scope note: the server auto-wires from SIBLING producers only (action outputs and foreach items).
# Run-level and group-level inputs are named by artefact STRING in the palette, not by a class the
# blob carries, so they cannot be type-matched here; those slots are left for the user to wire and
# the validator to check — the wire the server does make is always validator-sound.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import (
    ActionNode,
    Binding,
    FromNode,
    GraphTopology,
    SlotTypes,
)
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import Artifact


class AutoWire:
    """Static resolver of the unambiguous bindings a newly added node should adopt."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AutoWire is a static-only class and cannot be instantiated.")

    @classmethod
    def bindings_for(
        cls, container: GroupNodeBlob, new_id: str, node_class: type[ActionNode]
    ) -> dict[str, Binding]:
        """
        Compute the bindings to auto-adopt for ``new_id`` (its chaining edge already in place).

        Args:
            container (GroupNodeBlob): The container holding the new node and its transitions.
            new_id (str): Id of the just-added node.
            node_class (type[ActionNode]): The new node's registered class (its Consumes face).

        Returns:
            dict[str, Binding]: Slot name → binding, for every slot with exactly one sound source.
        """
        # 1. Upstream reachability AFTER the new edge — the validator's own ancestor notion.
        child_ids = {node.id for node in container.nodes}
        ancestors = GraphTopology.ancestors(child_ids, container.transitions).get(new_id, set())

        # 2. Every (node_id, field) a sibling produces, with its decoded (element, is_list) type.
        sources = cls.__container_sources(container, new_id, ancestors)

        # 3. Per slot: keep the type-compatible sources; bind only when exactly one remains.
        bindings: dict[str, Binding] = {}
        for slot_name, field_info in node_class.Consumes.model_fields.items():
            consumer_element, consumer_is_list = SlotTypes.element(field_info.annotation)
            if consumer_element is None:
                continue
            matches = [
                (source_id, field_name)
                for source_id, field_name, element, is_list in sources
                if is_list == consumer_is_list and issubclass(element, consumer_element)
            ]
            if len(matches) == 1:
                source_id, field_name = matches[0]
                bindings[slot_name] = FromNode(node_id=source_id, field_name=field_name)
        return bindings

    @classmethod
    def __container_sources(
        cls, container: GroupNodeBlob, new_id: str, ancestors: set[str]
    ) -> list[tuple[str, str, type, bool]]:
        """Collect (node_id, field, element, is_list) for every upstream sibling producer field."""
        sources: list[tuple[str, str, type, bool]] = []
        for sibling in container.nodes:
            # 1. Only genuinely upstream siblings may feed the new node.
            if sibling.id == new_id or sibling.id not in ancestors:
                continue
            # 2. Read each sibling's typed outputs (action faces, or a foreach's collected items).
            for field_name, element, is_list in cls.__produces_of(sibling):
                sources.append((sibling.id, field_name, element, is_list))
        return sources

    @classmethod
    def __produces_of(cls, node: NodeBlob) -> list[tuple[str, type, bool]]:
        """Typed outputs of a blob node: (field, element, is_list) for each producible field."""
        # 1. Action node: read its registered class's Produces face (unknown kind -> no outputs).
        if isinstance(node, ActionNodeBlob):
            try:
                node_class = NodeRegistry.get(node.family, node.kind)
            except KeyError:
                return []
            if not issubclass(node_class, ActionNode):
                return []
            outputs: list[tuple[str, type, bool]] = []
            for field_name, field_info in node_class.Produces.model_fields.items():
                element, is_list = SlotTypes.element(field_info.annotation)
                if element is not None:
                    outputs.append((field_name, element, is_list))
            return outputs

        # 2. Foreach: a single 'items' field, a list of its body's uniform terminal artefact.
        if isinstance(node, ForEachNodeBlob):
            element = cls.__foreach_item_element(node)
            return [("items", element, True)] if element is not None else []

        # 3. Nested group: no statically typed Produces face (its outputs are dynamic).
        return []

    @classmethod
    def __foreach_item_element(cls, loop: ForEachNodeBlob) -> type | None:
        """The uniform artefact class each item collects into — mirrors ``ForEach.item_type()``.

        The validator types a ForEach's ``items`` from the collection contract: EVERY body terminal
        must be an action producing the SAME single Artifact-class slot. Reading only the FIRST
        terminal (as this once did) would auto-wire a body whose terminals DISAGREE to that first
        type — a binding the validator then rejects. So this walks every terminal and returns the
        type only when they agree, else None: no auto-wire, and the validator reports the invalid
        body (FOREACH_INVALID_BODY) rather than the two silently diverging.
        """
        # 1. The body terminals: children with no outgoing transition (mirror GraphTopology.exits).
        body = loop.body
        froms = {transition.from_node_id for transition in body.transitions}
        terminals = [node for node in body.nodes if node.id not in froms]
        if not terminals:
            return None
        # 2. Every terminal must be a registered action producing exactly one Artifact-class scalar.
        element_types: set[type] = set()
        for terminal in terminals:
            element = cls.__terminal_item_element(terminal)
            if element is None:
                return None
            element_types.add(element)
        # 3. Uniformity: one artefact class across every terminal (else the validator rejects it).
        return element_types.pop() if len(element_types) == 1 else None

    @classmethod
    def __terminal_item_element(cls, terminal: NodeBlob) -> type | None:
        """A single body-terminal's collectable Artifact type, or None if it breaks the contract."""
        # 1. Only a registered action node is a collectable terminal (a group/foreach never is).
        if not isinstance(terminal, ActionNodeBlob):
            return None
        try:
            node_class = NodeRegistry.get(terminal.family, terminal.kind)
        except KeyError:
            return None
        # 2. Exactly one Artifact-class scalar slot — scalars/lists are not collectable into items.
        if not issubclass(node_class, ActionNode) or len(node_class.Produces.model_fields) != 1:
            return None
        annotation = next(iter(node_class.Produces.model_fields.values())).annotation
        element, is_list = SlotTypes.element(annotation)
        if element is None or is_list or not issubclass(element, Artifact):
            return None
        return element


__all__ = ["AutoWire"]
