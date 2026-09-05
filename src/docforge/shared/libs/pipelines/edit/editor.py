# ====== Code Summary ======
# GraphEditor — applies a list of edit operations to a pipeline blob and returns the edited blob.
# It owns the HEALING SEMANTICS the client used to own (chain-from-terminal, auto-wire, bridge on
# remove, purge dangling references, fragment splicing) so no client re-implements them: the edit
# lives next to the invariants (the validator). It is stateless across calls (deep-copies its input,
# never mutates it) and, like PipelineBuilder / GraphValidator, is a LoggerClass instance held in
# CONTEXT — one shared, logged, injectable service. An impossible operation raises EditError with a
# precise message; a merely INVALID result is left for the builder/validator to report downstream.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, FromFirst, FromNode, OnSuccess, Transition
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)
from shared_libs.pipelines.registry import NodeRegistry

# ====== Local Project Imports ======
from .errors import EditError
from .fragment import FragmentRemap
from .operations import (
    AddLoop,
    AddNode,
    EditOperation,
    InsertFragment,
    RemoveNode,
    SetAfter,
    SetBinding,
    SetCondition,
    SetConfig,
    SetLoopProp,
)
from .topology import BlobTopology
from .wiring import AutoWire


class GraphEditor(LoggerClass):
    """Applies edit operations to a pipeline blob, healing the graph the way the client used to."""

    def __init__(self) -> None:
        LoggerClass.__init__(self)

    def __container(self, blob: GroupNodeBlob, path: list[str]) -> GroupNodeBlob:
        """Resolve a container path to its group blob (foreach body or nested group)."""
        group = blob
        for segment in path:
            child = BlobTopology.find_node(group, segment)
            if child is None:
                raise EditError(
                    f"unknown container path {path}: no node '{segment}' in '{group.id}'"
                )
            if isinstance(child, ForEachNodeBlob):
                group = child.body
            elif isinstance(child, GroupNodeBlob):
                group = child
            else:
                raise EditError(
                    f"container path {path}: '{segment}' is an action node, not a container"
                )
        return group

    def __node(self, container: GroupNodeBlob, node_id: str) -> NodeBlob:
        """Return an existing child of the container, or raise EditError naming the missing id."""
        node = BlobTopology.find_node(container, node_id)
        if node is None:
            raise EditError(f"unknown node '{node_id}' in the addressed container")
        return node

    def __resolve_action_class(self, family: str, kind: str) -> type[ActionNode]:
        """Resolve (family, kind) to a registered action class, or raise EditError."""
        try:
            node_class = NodeRegistry.get(family, kind)
        except KeyError as exc:
            raise EditError(f"unknown node '{family}/{kind}': {exc}") from exc
        if not issubclass(node_class, ActionNode):
            raise EditError(f"'{family}/{kind}' is not an action node and cannot be added")
        return node_class

    def __mint_id(self, blob: GroupNodeBlob, explicit: str | None, base: str) -> str:
        """Use an explicit id (unique or reject) or derive a fresh one from ``base``."""
        if explicit is not None:
            if explicit in BlobTopology.all_node_ids(blob):
                raise EditError(f"duplicate node id '{explicit}'")
            return explicit
        return BlobTopology.fresh_id(blob, base)

    @staticmethod
    def __default_config(node_class: type[ActionNode]) -> dict:
        """Config prefilled from the class's schema defaults; required (default-less) fields skipped."""
        return {
            name: field.get_default(call_default_factory=True)
            for name, field in node_class.Config.model_fields.items()
            if not field.is_required()
        }

    def __add_node(self, blob: GroupNodeBlob, op: AddNode) -> None:
        """Append an action node, chain it from the terminal, auto-wire its unambiguous slots."""
        container = self.__container(blob, op.container)
        node_class = self.__resolve_action_class(op.family, op.kind)
        node_id = self.__mint_id(blob, op.node_id, op.kind)
        # 1. Read the terminal BEFORE adding — the new node chains from the current tail.
        tail = BlobTopology.terminal_of(container)
        container.nodes.append(
            ActionNodeBlob(
                id=node_id, family=op.family, kind=op.kind, config=self.__default_config(node_class)
            )
        )
        # 2. Chain first, wire second: upstream-ness only exists once the edge is in place.
        if tail is not None:
            container.transitions.append(Transition(from_node_id=tail.id, to_node_id=node_id))
        bindings = AutoWire.bindings_for(container, node_id, node_class)
        if bindings:
            container.bindings[node_id] = bindings

    def __add_loop(self, blob: GroupNodeBlob, op: AddLoop) -> None:
        """Append a foreach loop over the given list binding, chained from the terminal."""
        container = self.__container(blob, op.container)
        node_id = self.__mint_id(blob, op.node_id, "loop")
        tail = BlobTopology.terminal_of(container)
        container.nodes.append(
            ForEachNodeBlob(
                id=node_id,
                over=op.over,
                item_field=op.item_field,
                max_concurrency=op.max_concurrency,
                body=GroupNodeBlob(id=f"{node_id}_body"),
            )
        )
        if tail is not None:
            container.transitions.append(Transition(from_node_id=tail.id, to_node_id=node_id))

    def __remove_node(self, blob: GroupNodeBlob, op: RemoveNode) -> None:
        """Drop a node, bridge a single-in/single-out chain, purge every dangling reference."""
        container = self.__container(blob, op.container)
        self.__node(container, op.node_id)

        # 0. A sibling ForEach's 'over' is a REQUIRED binding on the loop (not a slot in
        #    container.bindings), so __purge_references cannot unbind it the way it heals other
        #    data bindings — and there is no source to bridge it to (the control chain is not the
        #    data source). Removing its source would leave the loop iterating over a node that no
        #    longer exists — a broken graph — so refuse the removal, mirroring set_after's refusal
        #    to leave a valid-but-wrong graph, and point the caller at set_loop_prop.
        orphaned = sorted(
            node.id
            for node in container.nodes
            if isinstance(node, ForEachNodeBlob)
            and isinstance(node.over, FromNode)
            and node.over.node_id == op.node_id
        )
        if orphaned:
            raise EditError(
                f"cannot remove '{op.node_id}': foreach {', '.join(orphaned)} iterate(s) over it "
                f"(its 'over' is a required binding); re-point the loop with set_loop_prop first"
            )

        incoming = [t for t in container.transitions if t.to_node_id == op.node_id]
        outgoing = [t for t in container.transitions if t.from_node_id == op.node_id]

        # 1. Remove the node and every transition that touched it.
        container.nodes = [n for n in container.nodes if n.id != op.node_id]
        container.transitions = [
            t
            for t in container.transitions
            if t.from_node_id != op.node_id and t.to_node_id != op.node_id
        ]

        # 2. Bridge A -> X -> B into A -> B, keeping the incoming edge's condition.
        if len(incoming) == 1 and len(outgoing) == 1:
            source, target = incoming[0].from_node_id, outgoing[0].to_node_id
            already = any(
                t.from_node_id == source and t.to_node_id == target for t in container.transitions
            )
            if not already:
                container.transitions.append(
                    Transition(
                        from_node_id=source, to_node_id=target, condition=incoming[0].condition
                    )
                )

        # 3. Drop the node's own wiring and purge references to it in every other node's bindings.
        container.bindings.pop(op.node_id, None)
        self.__purge_references(container, op.node_id)

    @staticmethod
    def __purge_references(container: GroupNodeBlob, removed_id: str) -> None:
        """Unbind FromNode slots pointing at ``removed_id``; trim FromFirst candidates, drop if empty."""
        for slots in container.bindings.values():
            for slot, binding in list(slots.items()):
                if isinstance(binding, FromNode) and binding.node_id == removed_id:
                    del slots[slot]
                elif isinstance(binding, FromFirst):
                    kept = [c for c in binding.candidates if c.node_id != removed_id]
                    if not kept:
                        del slots[slot]
                    elif len(kept) != len(binding.candidates):
                        slots[slot] = FromFirst(candidates=kept)

    def __set_binding(self, blob: GroupNodeBlob, op: SetBinding) -> None:
        """Bind one input slot, or (binding=None) unbind it — a missing slot is a clean no-op."""
        container = self.__container(blob, op.container)
        self.__node(container, op.node_id)
        if op.binding is None:
            slots = container.bindings.get(op.node_id)
            if slots is not None:
                slots.pop(op.slot, None)
            return
        container.bindings.setdefault(op.node_id, {})[op.slot] = op.binding

    def __set_after(self, blob: GroupNodeBlob, op: SetAfter) -> None:
        """Replace a node's single incoming transition; from_node_id=None detaches it entirely."""
        container = self.__container(blob, op.container)
        self.__node(container, op.node_id)
        incoming = [t for t in container.transitions if t.to_node_id == op.node_id]
        # SetAfter repositions a node by REPLACING its single incoming edge. A convergence node has
        # several incoming edges (e.g. a FromFirst join after a branch), so "the" edge to replace is
        # ambiguous — silently dropping the others would leave a valid-but-wrong graph. Refuse it and
        # point the caller at the precise-edge operations instead.
        if len(incoming) > 1:
            sources = ", ".join(sorted(t.from_node_id for t in incoming))
            raise EditError(
                f"cannot set_after on convergence node '{op.node_id}': it has {len(incoming)} "
                f"incoming edges ({sources}); re-point a specific edge with set_condition or "
                f"remove_node instead"
            )
        previous = incoming[0] if incoming else None
        container.transitions = [t for t in container.transitions if t.to_node_id != op.node_id]
        if op.from_node_id is None:
            return
        self.__node(container, op.from_node_id)
        condition = previous.condition if previous is not None else OnSuccess()
        container.transitions.append(
            Transition(from_node_id=op.from_node_id, to_node_id=op.node_id, condition=condition)
        )

    def __set_condition(self, blob: GroupNodeBlob, op: SetCondition) -> None:
        """Replace the condition on the existing edge between two nodes."""
        container = self.__container(blob, op.container)
        edge = next(
            (
                t
                for t in container.transitions
                if t.from_node_id == op.from_node_id and t.to_node_id == op.to_node_id
            ),
            None,
        )
        if edge is None:
            raise EditError(f"no transition '{op.from_node_id}' -> '{op.to_node_id}' to re-gate")
        edge.condition = op.condition

    def __set_config(self, blob: GroupNodeBlob, op: SetConfig) -> None:
        """Replace an action node's whole config dict."""
        container = self.__container(blob, op.container)
        node = self.__node(container, op.node_id)
        if not isinstance(node, ActionNodeBlob):
            raise EditError(f"node '{op.node_id}' is not an action node and has no config")
        node.config = dict(op.config)

    def __set_loop_prop(self, blob: GroupNodeBlob, op: SetLoopProp) -> None:
        """Update a foreach loop's item_field / max_concurrency / over (only the provided ones)."""
        container = self.__container(blob, op.container)
        node = self.__node(container, op.node_id)
        if not isinstance(node, ForEachNodeBlob):
            raise EditError(f"node '{op.node_id}' is not a foreach loop")
        if op.item_field is not None:
            node.item_field = op.item_field
        if op.max_concurrency is not None:
            node.max_concurrency = op.max_concurrency
        if op.over is not None:
            node.over = op.over

    def __insert_fragment(self, blob: GroupNodeBlob, op: InsertFragment) -> None:
        """Splice a fragment's contents into a container: disambiguate ids, chain every root."""
        container = self.__container(blob, op.container)
        fragment = op.fragment.model_copy(deep=True)
        mapping = FragmentRemap.id_map(fragment, op.overrides, BlobTopology.all_node_ids(blob))
        renamed = FragmentRemap.remap(fragment, mapping)

        # 1. The tail BEFORE splicing; the fragment roots (no internal incoming edge) chain onto it.
        tail = BlobTopology.terminal_of(container)
        internal_targets = {t.to_node_id for t in renamed.transitions}
        roots = [node for node in renamed.nodes if node.id not in internal_targets]

        # 2. The fragment's wrapper group is discarded — only its contents land in the container.
        container.nodes.extend(renamed.nodes)
        container.transitions.extend(renamed.transitions)
        container.bindings.update(renamed.bindings)
        if tail is not None:
            for root in roots:
                container.transitions.append(Transition(from_node_id=tail.id, to_node_id=root.id))

    def __apply_one(self, blob: GroupNodeBlob, op: EditOperation) -> None:
        """Dispatch a single operation to its handler (mutating ``blob`` in place)."""
        match op:
            case AddNode():
                self.__add_node(blob, op)
            case AddLoop():
                self.__add_loop(blob, op)
            case RemoveNode():
                self.__remove_node(blob, op)
            case SetBinding():
                self.__set_binding(blob, op)
            case SetAfter():
                self.__set_after(blob, op)
            case SetCondition():
                self.__set_condition(blob, op)
            case SetConfig():
                self.__set_config(blob, op)
            case SetLoopProp():
                self.__set_loop_prop(blob, op)
            case InsertFragment():
                self.__insert_fragment(blob, op)

    def apply(self, blob: GroupNodeBlob, operations: list[EditOperation]) -> GroupNodeBlob:
        """
        Apply edit operations to a blob, in order, returning the edited copy.

        Args:
            blob (GroupNodeBlob): The pipeline blob to edit (never mutated — deep-copied first).
            operations (list[EditOperation]): The operations to apply, in order.

        Returns:
            GroupNodeBlob: The edited blob (build/validate it to learn whether it is coherent).

        Raises:
            EditError: On an impossible operation (unknown container/node/kind, duplicate id, …).
        """
        # 1. Work on a deep copy so the caller's blob (and the EditError echo) stays intact.
        edited = blob.model_copy(deep=True)

        # 2. Apply each operation in order; the first impossible one aborts with a precise error.
        for index, op in enumerate(operations):
            self.logger.debug(f"applying op {index} '{op.op}'")
            self.__apply_one(edited, op)

        self.logger.info(f"applied {len(operations)} edit operation(s) to '{edited.id}'")
        return edited


__all__ = ["GraphEditor"]
