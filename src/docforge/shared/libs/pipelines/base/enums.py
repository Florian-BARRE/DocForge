# ====== Code Summary ======
# Base enumerations that classify nodes in the pipeline graph. Kept in their own module so both
# the node contract (node.py) and the description payload (describe.py) can import them without
# creating an import cycle.

# ====== Standard Library Imports ======
from enum import StrEnum


class NodeType(StrEnum):
    """
    The three shapes a graph node can take.

    Attributes:
        ACTION: A leaf node that performs work through a provider/brick.
        GROUP: A sub-graph of child nodes wired together by transitions.
        FOREACH: A sub-graph run once per item of a list, results collected in order.
    """

    ACTION = "action"
    GROUP = "group"
    FOREACH = "foreach"


__all__ = ["NodeType"]
