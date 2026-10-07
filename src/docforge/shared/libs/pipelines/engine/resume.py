# ====== Code Summary ======
# ResumePoint — the engine seam for starting a run MID-GRAPH (the replay-from-stage mode). A replay
# re-runs only the stages downstream of an already-persisted point: the caller pre-fills the outputs of
# the upstream ROOT nodes the downstream bindings read (rebuilt from persisted state, never run) and
# names the root node the walk starts at. The engine stays generic and pure: it only seeds its root
# ``node_outputs`` with these values and begins at ``start_node_id`` instead of the entry — the
# downstream nodes resolve their FromNode/FromFirst bindings exactly as in a full run.

# ====== Standard Library Imports ======
from collections.abc import Mapping
from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeOutput


@dataclass(frozen=True, slots=True)
class ResumePoint:
    """
    Where a mid-graph run starts and the upstream outputs it stands on.

    Attributes:
        start_node_id (str): The ROOT child the walk starts at (instead of the group's entry).
        seeded_outputs (Mapping[str, NodeOutput]): Root node id → the output that node WOULD have
            produced, pre-filled into the root group's outputs so downstream bindings resolve. Only
            the fields a downstream binding reads need to be set.
        downstream_ids (frozenset[str]): The root node ids the resumed walk may run (the start node
            and everything reachable from it) — the caller's scope for preflight and progress; the
            engine itself follows transitions and does not read it.
    """

    start_node_id: str
    seeded_outputs: Mapping[str, NodeOutput] = field(default_factory=dict)
    downstream_ids: frozenset[str] = field(default_factory=frozenset)


__all__ = ["ResumePoint"]
