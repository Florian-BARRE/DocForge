# ====== Code Summary ======
# The run-context primitives — the vertical (capability) axis and the per-node Scope.
#   - CapabilityRef: how a node NAMES a capability it requires (a serialisable Pydantic descriptor).
#   - CapabilityRegistry: a hierarchical store. Resolution walks UP the ancestor chain, so a deeper
#     level specialises/overrides the broader one — the "more specialised the deeper you go"
#     mechanism, expressed as lexical-scope resolution.
#   - CapabilityView: the resolved, read-only set handed to a node for its run.
#   - Scope: what a leaf node receives in execute() — its resolved typed Input + its capabilities.
#   - RunContext: the run-wide state (the pipeline input + the root capability registry) that flows
#     down to every descendant.
# The registry / view / scope / run-context are runtime CARRIERS: they hold live infrastructure
# handles (S3/Postgres/Qdrant clients) that are not serialisable by nature, so they stay lightweight
# dataclasses — only the descriptive CapabilityRef is a Pydantic model.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict

# ====== Local Project Imports ======
from .errors import ResolutionError
from .io import NodeInput

InputT = TypeVar("InputT", bound=NodeInput)


class CapabilityRef(BaseModel):
    """
    A serialisable reference to a capability a node requires (resolved up the ancestor chain).

    Attributes:
        name (str): Lookup name in the capability registry (e.g. ``"s3"``, ``"ocr_chain"``).
        description (str): One-line description, surfaced by describe().
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    """
    Hierarchical capability store — the vertical resolution axis (runtime carrier).

    A node entering the tree may push a child registry carrying its own (more specialised)
    capabilities; resolution checks the local layer first, then walks up to the parent, so a local
    capability overrides a broader ancestor one.

    Attributes:
        items (dict[str, Any]): Capabilities provided at THIS level (live handles, not serialisable).
        parent (CapabilityRegistry | None): The enclosing (broader) level, or None at the root.
    """

    items: dict[str, Any] = field(default_factory=dict)
    parent: "CapabilityRegistry | None" = None

    def resolve(self, name: str) -> Any | None:
        """
        Resolve a capability by name, local layer first then up the ancestor chain.

        Args:
            name (str): Capability lookup name.

        Returns:
            Any | None: The capability, or None when no level provides it.
        """
        if name in self.items:
            return self.items[name]
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

    def child(self, items: dict[str, Any]) -> "CapabilityRegistry":
        """
        Return a new registry layer that specialises this one with ``items``.

        Args:
            items (dict[str, Any]): Capabilities owned by the deeper level.

        Returns:
            CapabilityRegistry: A child registry whose parent is ``self``.
        """
        return CapabilityRegistry(items=items, parent=self)


@dataclass(frozen=True, slots=True)
class CapabilityView:
    """
    The resolved, read-only capabilities handed to a single node for its run (runtime carrier).

    Attributes:
        items (dict[str, Any]): Resolved name -> capability (exactly the node's declared ``REQUIRES``).
    """

    items: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Any | None:
        """Return a resolved capability by name, or None if the node did not require it."""
        return self.items.get(name)

    def require(self, name: str) -> Any:
        """
        Return a resolved capability by name, raising when absent.

        Args:
            name (str): Capability name (must be in the node's declared ``REQUIRES``).

        Returns:
            Any: The resolved capability.

        Raises:
            ResolutionError: When the capability was not resolved for this node.
        """
        if name not in self.items:
            raise ResolutionError(
                f"Capability {name!r} was not resolved for this node (is it in REQUIRES?).",
                code="capability_missing",
            )
        return self.items[name]


@dataclass(frozen=True, slots=True)
class Scope(Generic[InputT]):
    """
    Everything a leaf node receives to do its work: its resolved input + its capabilities.

    Attributes:
        input (InputT): The node's typed, verified Input (built by the resolver).
        capabilities (CapabilityView): The resolved capabilities the node declared it requires.
    """

    input: InputT
    capabilities: CapabilityView


@dataclass(slots=True)
class RunContext:
    """
    Run-wide state that flows down to every descendant of the root pipeline (runtime carrier).

    Attributes:
        run_input (NodeInput): The pipeline's input — the source of every ``FromRunInput`` binding.
        capabilities (CapabilityRegistry): The root capability registry (broadest level).
    """

    run_input: NodeInput
    capabilities: CapabilityRegistry


__all__ = [
    "CapabilityRef",
    "CapabilityRegistry",
    "CapabilityView",
    "Scope",
    "RunContext",
]
