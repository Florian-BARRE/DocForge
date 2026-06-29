# ====== Code Summary ======
# The context layer — what every node receives to do its work, as a hierarchical class tree that
# mirrors the node tree. ``ContextBase`` is the universal machinery (the node's resolved ``input``,
# the ``services`` it requires, and a ``parent`` link to walk up). The three KIND bases
# (PipelineContextBase / StageContextBase / StepContextBase) differentiate the levels; concrete nodes
# subclass the matching base in their own ``context.py`` and add typed accessors (``ctx.input`` /
# ``ctx.parser``). ``ServiceRef`` is how a node declares a service it needs; ``ServiceRegistry`` is the
# hierarchical store the engine resolves them from (a node author never touches it). ``RunContext`` is
# the engine's run-level handle (the run input + the root service registry).

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict

# ====== Local Project Imports ======
from .errors import ResolutionError
from .io import NodeInput


class ServiceRef(BaseModel):
    """
    A serialisable reference to a service a node requires (resolved up the registry chain).

    A *service* is a built, live handle a node uses to work — an S3/Postgres/Qdrant client or an
    instantiated brick from a ``capabilities/`` folder (e.g. a Parser). Declared in a node's
    ``REQUIRES``; the engine resolves it and exposes it on the node's context.

    Attributes:
        name (str): Lookup name in the service registry (e.g. ``"s3"``, ``"parser"``).
        description (str): One-line description, surfaced by describe().
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""


class ChainRef(ServiceRef):
    """
    A ServiceRef for a provider-escalation CHAIN — adds the provider ``category``.

    One declaration, two jobs:
    - RUNTIME (as a ServiceRef): the engine injects the BUILT chain under ``name`` (``ctx.<name>``).
    - DISCOVERY: ``category`` lets describe() enumerate the available providers for that category (the
      provider catalog) and emit the chain's config schema (gate + each provider's config), so the UI
      can render the per-collection chain editor with zero hardcoded text.

    Attributes:
        category (str): Provider category this chain serves (e.g. ``"ocr"``, ``"vlm"``, ``"parser"``,
            ``"embed"``, ``"llm"``, ``"classifier"``).
    """

    category: str


@dataclass(frozen=True, slots=True)
class ServiceRegistry:
    """
    Hierarchical service store — the vertical resolution axis (runtime carrier).

    A node entering the tree may push a child registry carrying its own (more specialised) services;
    resolution checks the local layer first, then walks up to the parent, so a local service
    overrides a broader ancestor one.

    Attributes:
        items (dict[str, Any]): Services provided at THIS level (live handles, not serialisable).
        parent (ServiceRegistry | None): The enclosing (broader) level, or None at the root.
    """

    items: dict[str, Any] = field(default_factory=dict)
    parent: "ServiceRegistry | None" = None

    def resolve(self, name: str) -> Any | None:
        """Resolve a service by name, local layer first then up the ancestor chain."""
        if name in self.items:
            return self.items[name]
        if self.parent is not None:
            return self.parent.resolve(name)
        return None

    def child(self, items: dict[str, Any]) -> "ServiceRegistry":
        """Return a new registry layer that specialises this one with ``items``."""
        return ServiceRegistry(items=items, parent=self)


class ContextBase:
    """
    Universal machinery every node's context inherits — its input, its services, and its parent.

    Node authors never construct this; the engine builds the node's concrete ``Context`` subclass and
    hands it to ``execute``. Concrete contexts narrow ``input`` and add typed service accessors.
    """

    def __init__(
        self,
        node_input: NodeInput,
        services: dict[str, Any],
        parent: "ContextBase | None" = None,
    ) -> None:
        """
        Args:
            node_input (NodeInput): The node's resolved typed input.
            services (dict[str, Any]): The resolved services the node declared in ``REQUIRES``.
            parent (ContextBase | None): The parent node's context, or None at the root.
        """
        self._input = node_input
        self._services = services
        self._parent = parent

    @property
    def input(self) -> NodeInput:
        """The node's resolved typed input (concrete contexts narrow the return type)."""
        return self._input

    @property
    def parent(self) -> "ContextBase | None":
        """The parent node's context (walk up the tree), or None at the root."""
        return self._parent

    def service(self, name: str) -> Any:
        """
        Return a resolved service by name, raising when the node did not require it.

        Args:
            name (str): Service name (must be in the node's declared ``REQUIRES``).

        Raises:
            ResolutionError: When the service was not resolved for this node.
        """
        if name not in self._services:
            raise ResolutionError(
                f"Service {name!r} was not resolved for this node (is it in REQUIRES?).",
                code="service_missing",
            )
        return self._services[name]


class PipelineContextBase(ContextBase):
    """Base context for a pipeline-level node."""


class StageContextBase(ContextBase):
    """Base context for a stage-level node."""


class StepContextBase(ContextBase):
    """Base context for a step-level node."""


@dataclass(slots=True)
class RunContext:
    """
    The engine's run-level handle (not part of the per-node context tree).

    Attributes:
        run_input (NodeInput): The pipeline's input — the source of every ``FromRunInput`` binding.
        services (ServiceRegistry): The root service registry (broadest level).
    """

    run_input: NodeInput
    services: ServiceRegistry


__all__ = [
    "ServiceRef",
    "ChainRef",
    "ServiceRegistry",
    "ContextBase",
    "PipelineContextBase",
    "StageContextBase",
    "StepContextBase",
    "RunContext",
]
