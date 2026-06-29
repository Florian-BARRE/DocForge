# ====== Code Summary ======
# The IO contract layer. Every node declares a typed Input/Output (Pydantic models). Each Input
# FIELD is annotated with a declarative *binding* (FromSibling / FromParent / FromRunInput) that
# names the source the engine must resolve it from — across siblings, down from the parent, or from
# the run input. This single declaration is what the DAG order, the fingerprint inputs, describe(),
# and the resolver all derive from. ``input_bindings`` extracts those markers for the resolver.
# Everything here is serialisable Pydantic — depends only on Pydantic, so the contract layer stays
# at the bottom of the DAG.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Annotated, get_args, get_origin, get_type_hints

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict


class NodeInput(BaseModel):
    """
    Base class for a node's typed input contract.

    Fields are immutable once resolved (``frozen``) and may hold domain objects
    (``arbitrary_types_allowed``) such as the IR or chunk lists carried between stages.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)


class NodeOutput(BaseModel):
    """Base class for a node's typed output contract."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class CompositeOutput(NodeOutput):
    """
    Default output of a composite node — the map of its children's outputs.

    Concrete pipelines/stages override ``aggregate`` to return their own typed output; this is the
    structural fallback so a composite always has a well-formed output.

    Attributes:
        children (dict[str, NodeOutput]): Child key -> child output produced this run.
    """

    children: dict[str, NodeOutput] = {}


class Source(BaseModel):
    """Serialisable marker base for an input-field binding source (resolved by the engine)."""

    model_config = ConfigDict(frozen=True)


class FromSibling(Source):
    """
    Bind an input field to the output of a sibling node (the horizontal data axis).

    This is what makes non-linear dependencies explicit: a stage can pull the output of ANY upstream
    sibling, not just the previous one. The set of ``producer`` keys across a node's input bindings
    IS the node's dependency set — the DAG order and the fingerprint inputs both derive from it.

    Attributes:
        producer (str): Key of the sibling node whose output fills this field.
        field (str | None): Optional attribute of that output to extract; ``None`` = the whole output.
        required (bool): When ``True`` (default), a missing/None value raises a ``ResolutionError``.
    """

    producer: str
    field: str | None = None
    required: bool = True


class FromParent(Source):
    """
    Bind an input field to a field of the PARENT composite's resolved input (the down axis).

    This is how data flows DOWN one level: a step reads a field its stage received (which the stage
    itself resolved from upstream stages), without that field having to be a global run input.

    Attributes:
        field (str | None): Name of the parent-input field; ``None`` = same name as the bound field.
        required (bool): When ``True`` (default), a missing/None value raises a ``ResolutionError``.
    """

    field: str | None = None
    required: bool = True


class FromRunInput(Source):
    """
    Bind an input field to a field of the pipeline run input (available to every descendant).

    Attributes:
        field (str | None): Name of the run-input field; ``None`` = same name as the bound field.
        required (bool): When ``True`` (default), a missing/None value raises a ``ResolutionError``.
    """

    field: str | None = None
    required: bool = True


def input_bindings(model: type[NodeInput]) -> dict[str, Source]:
    """
    Extract the declarative binding of every annotated field of an Input model.

    Args:
        model (type[NodeInput]): The node's Input class.

    Returns:
        dict[str, Source]: Field name -> its binding ``Source`` (fields without a binding are
            omitted; they are expected to carry a default).
    """
    # 1. Resolve annotations WITH their Annotated extras so the binding markers survive.
    hints = get_type_hints(model, include_extras=True)

    # 2. Pick the first Source marker found in each field's Annotated metadata.
    bindings: dict[str, Source] = {}
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            for meta in get_args(hint)[1:]:
                if isinstance(meta, Source):
                    bindings[name] = meta
                    break
    return bindings


__all__ = [
    "NodeInput",
    "NodeOutput",
    "CompositeOutput",
    "Source",
    "FromSibling",
    "FromParent",
    "FromRunInput",
    "input_bindings",
]
