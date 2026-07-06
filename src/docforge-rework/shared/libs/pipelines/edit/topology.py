# ====== Code Summary ======
# Pure blob-topology helpers shared by every edit operation: order a container's nodes by their
# transition chain (to find the terminal a new node chains from), collect every node id in the
# whole blob (to mint fresh, collision-free ids), and look a node up in a container. These are the
# exact structural notions the client editor relies on (orderedNodes / terminalOf / allNodeIds /
# freshId), ported once here so server and client heal a graph identically. No I/O, no logging.

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import ForEachNodeBlob, GroupNodeBlob, NodeBlob


class BlobTopology:
    """Static, side-effect-free reading of a blob's node/transition structure."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BlobTopology is a static-only class and cannot be instantiated.")

    @classmethod
    def ordered_nodes(cls, group: GroupNodeBlob) -> list[NodeBlob]:
        """
        Order a container's nodes by following the transition chain from its entry.

        Mirrors the client's ``orderedNodes``: start at the first node with no incoming edge,
        walk its outgoing chain, then append any unwired nodes last (in insertion order).

        Args:
            group (GroupNodeBlob): The container whose nodes to order.

        Returns:
            list[NodeBlob]: The nodes in display/chain order.
        """
        # 1. The entry is the first node that is never a transition target.
        targets = {transition.to_node_id for transition in group.transitions}
        seen: set[str] = set()
        sequence: list[NodeBlob] = []
        current = next((node for node in group.nodes if node.id not in targets), None)

        # 2. Follow the single outgoing edge from each node until the chain ends or loops.
        while current is not None and current.id not in seen:
            sequence.append(current)
            seen.add(current.id)
            edge = next((t for t in group.transitions if t.from_node_id == current.id), None)
            current = (
                next((n for n in group.nodes if n.id == edge.to_node_id), None) if edge else None
            )

        # 3. Any node the chain never reached lands at the end, in insertion order.
        sequence.extend(node for node in group.nodes if node.id not in seen)
        return sequence

    @classmethod
    def terminal_of(cls, group: GroupNodeBlob) -> NodeBlob | None:
        """
        The node a freshly added child chains from — the last of the ordered chain.

        Args:
            group (GroupNodeBlob): The container to read.

        Returns:
            NodeBlob | None: The terminal node, or None when the container is empty.
        """
        sequence = cls.ordered_nodes(group)
        return sequence[-1] if sequence else None

    @classmethod
    def all_node_ids(cls, blob: GroupNodeBlob) -> set[str]:
        """
        Every node id used ANYWHERE in the blob (nested foreach bodies and groups included).

        Args:
            blob (GroupNodeBlob): The root graph.

        Returns:
            set[str]: All action, foreach and nested-group ids in the tree.
        """
        ids: set[str] = set()

        def walk(nodes: list[NodeBlob]) -> None:
            for node in nodes:
                ids.add(node.id)
                if isinstance(node, ForEachNodeBlob):
                    walk(node.body.nodes)
                elif isinstance(node, GroupNodeBlob):
                    walk(node.nodes)

        walk(blob.nodes)
        return ids

    @classmethod
    def fresh_id(cls, blob: GroupNodeBlob, base: str) -> str:
        """
        A graph-unique id derived from ``base`` (``base``, then ``base_2``, ``base_3``, …).

        Args:
            blob (GroupNodeBlob): The root graph, scanned for every existing id.
            base (str): The preferred id stem (usually the node's kind).

        Returns:
            str: The first available id.
        """
        taken = cls.all_node_ids(blob)
        candidate, suffix = base, 2
        while candidate in taken:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    @classmethod
    def find_node(cls, group: GroupNodeBlob, node_id: str) -> NodeBlob | None:
        """
        Return the direct child of ``group`` with ``node_id``, or None when absent.

        Args:
            group (GroupNodeBlob): The container to look in.
            node_id (str): The child id to find.

        Returns:
            NodeBlob | None: The matching child node, or None.
        """
        return next((node for node in group.nodes if node.id == node_id), None)


__all__ = ["BlobTopology"]
