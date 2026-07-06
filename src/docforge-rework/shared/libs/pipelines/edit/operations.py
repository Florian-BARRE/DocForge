# ====== Code Summary ======
# The edit operations — one Pydantic model per graph mutation, joined into a discriminated union
# on the ``op`` tag. Each model is extra="forbid" and every field is described, so the operation
# vocabulary is self-documenting (it feeds the same backend-driven UI as the palette). Operations
# transform BLOBS (the serialised graph); the GraphEditor applies them, then the graph is rebuilt
# and validated. A container is addressed by a list of foreach/group node ids from the root
# (``[]`` = the root graph itself), mirroring the client's container-path notion exactly.

# ====== Standard Library Imports ======
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, Condition
from shared_libs.pipelines.build.blob import GroupNodeBlob

# The container path shared by every operation — declared once so its meaning never drifts.
_CONTAINER = Field(
    default_factory=list,
    description="Path of foreach/group node ids from the root to the container to edit; [] = root.",
)


class AddNode(BaseModel):
    """Append an action node to a container, chain it from the terminal, auto-wire sound slots."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add_node"] = "add_node"
    family: str = Field(description="Registry family of the node to add (e.g. 'ocr', 'chunker').")
    kind: str = Field(description="Registry kind within the family (e.g. 'structure_aware').")
    node_id: str | None = Field(
        default=None,
        description="Explicit graph-unique id; when absent the server derives a fresh id from kind.",
    )
    container: list[str] = _CONTAINER


class AddLoop(BaseModel):
    """Append a foreach loop over a list binding, chained from the container terminal."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add_loop"] = "add_loop"
    over: Binding = Field(description="The upstream list field the loop iterates.")
    node_id: str | None = Field(
        default=None,
        description="Explicit graph-unique id; when absent the server derives a fresh id from 'loop'.",
    )
    item_field: str = Field(
        default="item", description="Group-input field each item is exposed under to the body."
    )
    max_concurrency: int = Field(
        default=4, ge=1, description="How many items may run their body at the same time."
    )
    container: list[str] = _CONTAINER


class RemoveNode(BaseModel):
    """Drop a node with its wiring, bridge a single-in/single-out chain, purge dangling references."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["remove_node"] = "remove_node"
    node_id: str = Field(description="Id of the node (action, foreach or group) to remove.")
    container: list[str] = _CONTAINER


class SetBinding(BaseModel):
    """Set or clear the binding feeding one input slot of a node (None unbinds the slot)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_binding"] = "set_binding"
    node_id: str = Field(description="Id of the node whose input slot is (re)wired.")
    slot: str = Field(description="Name of the consumed input slot to bind.")
    binding: Binding | None = Field(
        description="The source to read the slot from; null unbinds the slot (a no-op if unset)."
    )
    container: list[str] = _CONTAINER


class SetAfter(BaseModel):
    """Reposition a node: replace its single incoming transition (None detaches it entirely)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_after"] = "set_after"
    node_id: str = Field(description="Id of the node to reposition.")
    from_node_id: str | None = Field(
        description="New predecessor; the incoming edge's condition is preserved. Null detaches."
    )
    container: list[str] = _CONTAINER


class SetCondition(BaseModel):
    """Replace the condition gating an existing transition between two nodes."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_condition"] = "set_condition"
    from_node_id: str = Field(description="Source node of the transition to re-gate.")
    to_node_id: str = Field(description="Target node of the transition to re-gate.")
    condition: Condition = Field(description="The new condition (always/on_*/score_below/when_equals).")
    container: list[str] = _CONTAINER


class SetConfig(BaseModel):
    """Replace an action node's whole config dict (validated against its Config at build time)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_config"] = "set_config"
    node_id: str = Field(description="Id of the action node whose config is replaced.")
    config: dict = Field(description="The new config dict (full replacement, not a merge).")
    container: list[str] = _CONTAINER


class SetLoopProp(BaseModel):
    """Update one or more properties of a foreach loop (item_field / max_concurrency / over)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["set_loop_prop"] = "set_loop_prop"
    node_id: str = Field(description="Id of the foreach loop to update.")
    item_field: str | None = Field(
        default=None, description="New group-input field name each item is exposed under."
    )
    max_concurrency: int | None = Field(
        default=None, ge=1, description="New per-item body concurrency."
    )
    over: Binding | None = Field(default=None, description="New list binding the loop iterates.")
    container: list[str] = _CONTAINER


class InsertFragment(BaseModel):
    """Splice a pre-wired fragment's contents into a container (ids disambiguated, roots chained)."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["insert_fragment"] = "insert_fragment"
    fragment: GroupNodeBlob = Field(
        description="The recipe group whose CONTENTS are spliced in (its wrapper group is discarded)."
    )
    overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Preferred new ids per original fragment id; collisions still get _N suffixes.",
    )
    container: list[str] = _CONTAINER


# Discriminated union — Pydantic selects the operation from its ``op`` tag on load.
type EditOperation = Annotated[
    AddNode
    | AddLoop
    | RemoveNode
    | SetBinding
    | SetAfter
    | SetCondition
    | SetConfig
    | SetLoopProp
    | InsertFragment,
    Field(discriminator="op"),
]


__all__ = [
    "AddNode",
    "AddLoop",
    "RemoveNode",
    "SetBinding",
    "SetAfter",
    "SetCondition",
    "SetConfig",
    "SetLoopProp",
    "InsertFragment",
    "EditOperation",
]
