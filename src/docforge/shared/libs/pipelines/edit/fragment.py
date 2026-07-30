# ====== Code Summary ======
# Fragment id disambiguation + remap for insert_fragment. A recipe fragment carries placeholder
# ids that may collide with the target blob, so before splicing we build an id map (caller-supplied
# overrides first, then _N suffixes) covering EVERY id the fragment declares, and rewrite the
# fragment's nodes, transitions, bindings, foreach-over and nested bodies through it — recursively.
# ``{source: "group"}`` / ``{source: "run"}`` bindings carry no node id and pass through untouched,
# so a fragment dropped inside a loop body still reads that body's own group input. Ported 1:1 from
# the client's fragmentIds / renameGroupContents so both sides disambiguate identically.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, FromFirst, FromNode, Transition
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)


class FragmentRemap:
    """Static id-disambiguation and structural remap of an insertable fragment."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("FragmentRemap is a static-only class and cannot be instantiated.")

    @classmethod
    def id_map(
        cls, fragment: GroupNodeBlob, overrides: dict[str, str], taken: set[str]
    ) -> dict[str, str]:
        """
        Map every fragment id to a collision-free target id.

        Args:
            fragment (GroupNodeBlob): The fragment whose ids need disambiguating.
            overrides (dict[str, str]): Preferred new id per original id (applied first).
            taken (set[str]): Ids already used in the target blob.

        Returns:
            dict[str, str]: original id → final id (overrides honoured, then _N suffixes).
        """
        reserved = set(taken)
        mapping: dict[str, str] = {}
        for original in cls.__fragment_ids(fragment):
            base = overrides.get(original, original)
            candidate, suffix = base, 2
            while candidate in reserved:
                candidate = f"{base}_{suffix}"
                suffix += 1
            mapping[original] = candidate
            reserved.add(candidate)
        return mapping

    @classmethod
    def remap(cls, group: GroupNodeBlob, mapping: dict[str, str]) -> GroupNodeBlob:
        """
        Return a copy of ``group`` with every id (nodes, edges, bindings) rewritten via ``mapping``.

        Args:
            group (GroupNodeBlob): The group to rewrite (the fragment or a nested body).
            mapping (dict[str, str]): original id → final id.

        Returns:
            GroupNodeBlob: The remapped group (its own id is left for the caller to discard/set).
        """
        return GroupNodeBlob(
            id=group.id,
            nodes=[cls.__remap_node(node, mapping) for node in group.nodes],
            transitions=[
                Transition(
                    from_node_id=mapping.get(t.from_node_id, t.from_node_id),
                    to_node_id=mapping.get(t.to_node_id, t.to_node_id),
                    condition=t.condition,
                )
                for t in group.transitions
            ],
            bindings={
                mapping.get(node_id, node_id): {
                    slot: cls.__remap_binding(binding, mapping) for slot, binding in slots.items()
                }
                for node_id, slots in group.bindings.items()
            },
        )

    @classmethod
    def __fragment_ids(cls, fragment: GroupNodeBlob) -> list[str]:
        """Every node id the fragment declares, in order (its wrapper id excluded)."""
        ids: list[str] = []

        def walk(nodes: list[NodeBlob]) -> None:
            for node in nodes:
                ids.append(node.id)
                if isinstance(node, ForEachNodeBlob):
                    walk(node.body.nodes)
                elif isinstance(node, GroupNodeBlob):
                    walk(node.nodes)

        walk(fragment.nodes)
        return ids

    @classmethod
    def __remap_node(cls, node: NodeBlob, mapping: dict[str, str]) -> NodeBlob:
        """Rewrite a node's id (and, recursively, a foreach/group's contents) through the map."""
        new_id = mapping.get(node.id, node.id)
        # 1. Foreach: remap its id, its 'over' binding, and its body recursively.
        if isinstance(node, ForEachNodeBlob):
            return ForEachNodeBlob(
                id=new_id,
                over=cls.__remap_binding(node.over, mapping),
                item_field=node.item_field,
                max_concurrency=node.max_concurrency,
                body=cls.remap(node.body, mapping),
            )
        # 2. Nested group: remap its contents, then set its own new id.
        if isinstance(node, GroupNodeBlob):
            return cls.remap(node, mapping).model_copy(update={"id": new_id})
        # 3. Action node: only its id changes (family/kind/config carried over).
        return node.model_copy(update={"id": new_id}) if isinstance(node, ActionNodeBlob) else node

    @classmethod
    def __remap_binding(cls, binding: Binding, mapping: dict[str, str]) -> Binding:
        """Rewrite the node id(s) a binding names; run/group inputs pass through untouched."""
        if isinstance(binding, FromNode):
            return FromNode(
                node_id=mapping.get(binding.node_id, binding.node_id),
                field_name=binding.field_name,
            )
        if isinstance(binding, FromFirst):
            return FromFirst(
                candidates=[
                    FromNode(
                        node_id=mapping.get(candidate.node_id, candidate.node_id),
                        field_name=candidate.field_name,
                    )
                    for candidate in binding.candidates
                ]
            )
        return binding


__all__ = ["FragmentRemap"]
