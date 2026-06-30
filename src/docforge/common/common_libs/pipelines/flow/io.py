# ====== Code Summary ======
# The typed data contract of a node + its bindings. A node declares a typed Input (Pydantic) whose
# fields are each bound to a SOURCE: another sibling node's output (FromNode), the enclosing group's
# input (FromGroupInput), or the pipeline run input (FromRunInput). This is the DATA axis — orthogonal
# to transitions (the CONTROL axis): transitions decide which node runs, bindings decide what each node
# reads. Bindings are frozen dataclasses (a Pydantic model placed in Annotated metadata is mis-read by
# Pydantic as the field type, so the markers must stay dataclasses). NodeOutput is the typed result.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Annotated, Any, get_args, get_origin, get_type_hints

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict


class NodeInput(BaseModel):
    """Base of a node's typed input (its fields are bound to sources via Annotated markers)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class NodeOutput(BaseModel):
    """Base of a node's typed output. Outputs that feed a ``score_below`` edge expose a ``score``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


@dataclass(frozen=True, slots=True)
class FromNode:
    """Bind an input field to a sibling node's output field (defaults to the same field name)."""

    node: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class FromGroupInput:
    """Bind an input field to the enclosing group's input field (defaults to the same field name)."""

    field: str | None = None


@dataclass(frozen=True, slots=True)
class FromRunInput:
    """Bind an input field to the pipeline run input (defaults to the same field name)."""

    field: str | None = None
    required: bool = True


Source = FromNode | FromGroupInput | FromRunInput


def input_bindings(input_cls: type[NodeInput]) -> dict[str, Source]:
    """
    Extract a node Input's field bindings from its Annotated markers.

    Args:
        input_cls (type[NodeInput]): The node's typed Input class.

    Returns:
        dict[str, Source]: Field name -> its binding (FromNode / FromGroupInput / FromRunInput).
    """
    # 1. Walk the typed fields; keep those whose Annotated metadata carries a binding marker.
    bindings: dict[str, Source] = {}
    for name, hint in get_type_hints(input_cls, include_extras=True).items():
        if get_origin(hint) is Annotated:
            for meta in get_args(hint)[1:]:
                if isinstance(meta, (FromNode, FromGroupInput, FromRunInput)):
                    bindings[name] = meta
    return bindings


__all__ = ["NodeInput", "NodeOutput", "FromNode", "FromGroupInput", "FromRunInput", "Source", "input_bindings"]
