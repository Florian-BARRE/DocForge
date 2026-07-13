# ====== Code Summary ======
# PortBackedNode — the small ActionNode mixin every search node that needs the read store extends.
# It exposes the bound CollectionReadPort through a single typed accessor (self._read_port), so a
# retrieve/hydrate node never touches self._capabilities directly nor imports a client. Nodes that
# need no store (normalize, encode) subclass ActionNode straight — they take no port.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode

# ====== Local Project Imports ======
from ..ports import CollectionReadPort, read_port


class PortBackedNode(ActionNode):
    """An ActionNode that reaches the read-only store through its bound CollectionReadPort."""

    @property
    def _read_port(self) -> CollectionReadPort:
        """
        The CollectionReadPort injected via ``bind()``.

        Returns:
            CollectionReadPort: The bound read port.

        Raises:
            RuntimeError: If the node runs before its port was injected.
        """
        return read_port(self._capabilities)


__all__ = ["PortBackedNode"]
