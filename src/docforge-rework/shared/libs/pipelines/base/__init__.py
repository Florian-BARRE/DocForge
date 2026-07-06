# ---------------------- Node contract ---------------------- #
from .node import AbstractNode, ActionNode

# ---------------------- Group (sub-graph node) ---------------------- #
from .group import Group

# ---------------------- ForEach (per-item sub-graph node) ---------------------- #
from .foreach import ForEach, ForEachItems

# ---------------------- Graph topology ---------------------- #
from .graph import GraphTopology

# ---------------------- Slot shapes ---------------------- #
from .slots import SlotTypes

# ---------------------- Control flow (transitions) ---------------------- #
from .transition import (
    Always,
    Condition,
    ConditionKind,
    OnFailure,
    OnSuccess,
    ScoreBelow,
    WhenEquals,
    Transition,
)

# ---------------------- Data-plane contracts ---------------------- #
from .io import (
    NodeConfig,
    Binding,
    BindingSource,
    FromFirst,
    FromGroupInput,
    FromNode,
    FromRunInput,
    NodeInput,
    NodeOutput,
    ScoredOutput,
)

# ---------------------- Self-description ---------------------- #
from .describe import IoSlot, NodeDescription

# ---------------------- Classification enums ---------------------- #
from .enums import NodeType
from .errors import ErrorPolicy

# ---------------------- Execution trace ---------------------- #
from .execution import ErrorInfo, NodeExecutionRecord, NodeStatus

# ------------------- Public API ------------------- #
__all__ = [
    # node contract
    "AbstractNode",
    "ActionNode",
    # group
    "Group",
    # foreach
    "ForEach",
    "ForEachItems",
    # graph topology
    "GraphTopology",
    # slot shapes
    "SlotTypes",
    # control flow
    "ConditionKind",
    "Always",
    "OnSuccess",
    "OnFailure",
    "ScoreBelow",
    "WhenEquals",
    "Condition",
    "Transition",
    # data-plane contracts
    "BindingSource",
    "Binding",
    "FromFirst",
    "FromGroupInput",
    "FromNode",
    "FromRunInput",
    "NodeConfig",
    "NodeInput",
    "NodeOutput",
    "ScoredOutput",
    # self-description
    "IoSlot",
    "NodeDescription",
    # classification enums
    "NodeType",
    "ErrorPolicy",
    # execution trace
    "NodeStatus",
    "ErrorInfo",
    "NodeExecutionRecord",
]
