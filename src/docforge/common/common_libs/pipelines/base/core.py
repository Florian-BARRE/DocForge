# ====== Code Summary ======
# The universal node contracts — purely declarative, the engine does the running.
#   - AbstractNode: identity (SPEC/KIND), typed IO (Input/Output), required capabilities (REQUIRES),
#     and the derived ``consumes()`` (sibling producers, read from the Input bindings) + describe().
#     __init_subclass__ enforces that a concrete node declares its SPEC + KIND (loud at import).
#   - CompositeNode: a node whose work is its ordered children (pipeline over stages, stage over
#     steps). It only declares ``children`` + how to ``aggregate`` their outputs; the engine drives
#     the loop.
#   - LeafNode: a node that does real work in ``execute(scope)`` and returns its typed Output.
# A node knows NOTHING about scheduling, caching, fingerprinting, or error dispatch — all of that
# lives in the engine, so a node stays a small, testable, declarative box.

# ====== Standard Library Imports ======
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .config import NodeConfig
from .context import ChainRef, ContextBase, ServiceRef
from .errors import NodeError, PipelineError
from .io import CompositeOutput, FromSibling, NodeInput, NodeOutput, input_bindings
from .enums import ErrorPolicy, NodeKind
from .schema import ChainSchema, NodeSchema, ProviderSchema
from .spec import NodeSpec

InputT = TypeVar("InputT", bound=NodeInput)
OutputT = TypeVar("OutputT", bound=NodeOutput)

# Sentinel marking a forced ClassVar a concrete subclass has not declared.
_UNSET: Any = object()


class AbstractNode(ABC, LoggerClass, Generic[InputT, OutputT]):
    """
    Universal node contract — declarative identity + typed IO + required capabilities.

    A concrete node declares ``SPEC`` (identity + error policy), ``KIND`` (its level), ``Input`` /
    ``Output`` (typed contracts) and optionally ``REQUIRES`` (capabilities). Everything executive —
    ordering, resolution, caching, error dispatch, tracking — is the engine's job, never the node's.
    Intermediate abstract bases opt out of the SPEC/KIND check with ``abstract=True``.
    """

    SPEC: ClassVar[NodeSpec]
    KIND: ClassVar[NodeKind]
    Input: ClassVar[type[NodeInput]] = NodeInput
    Output: ClassVar[type[NodeOutput]] = NodeOutput
    Context: ClassVar[type[ContextBase]] = ContextBase
    # The node's per-collection configuration (the knobs the assembler fills from the stored JSON and
    # passes to __init__). Self-describing: describe() emits its JSON schema for the discovery UI. The
    # empty base means "no configurable knobs"; concrete nodes declare their own.
    Config: ClassVar[type[NodeConfig]] = NodeConfig
    # The error this node wraps a failure in: the engine wraps a failing child's error in the
    # parent's ``Error`` (building the recursive cause chain), and wraps a raw exception raised by a
    # leaf in its own ``Error``. Concrete nodes declare their level-specific class.
    Error: ClassVar[type[PipelineError]] = NodeError
    REQUIRES: ClassVar[tuple[ServiceRef, ...]] = ()

    def __init_subclass__(cls, *, abstract: bool = False, **kwargs: Any) -> None:
        """
        Enforce that a concrete node declares its forced ClassVars.

        Args:
            abstract (bool): Pass ``abstract=True`` for an intermediate base that specialises the
                contract without being runnable — it skips the check.

        Raises:
            TypeError: When a concrete subclass omits ``SPEC`` or ``KIND``.
        """
        super().__init_subclass__(**kwargs)
        if abstract:
            return
        for attr in ("SPEC", "KIND"):
            if getattr(cls, attr, _UNSET) is _UNSET:
                raise TypeError(f"{cls.__name__} is a concrete node but does not declare {attr}.")

    def __init__(self) -> None:
        """Initialise the node's logger."""
        LoggerClass.__init__(self)

    @property
    def key(self) -> str:
        """Stable node identifier (unique among its siblings)."""
        return self.SPEC.key

    @property
    def name(self) -> str:
        """Human-readable node name."""
        return self.SPEC.name

    @property
    def description(self) -> str:
        """One-line description of the node."""
        return self.SPEC.description

    @property
    def error_policy(self) -> ErrorPolicy:
        """The node's declarative (authoritative) error policy."""
        return self.SPEC.error_policy

    def consumes(self) -> tuple[str, ...]:
        """
        The sibling keys this node depends on — derived from its Input ``FromSibling`` bindings.

        This single derivation is the source of truth for both the DAG order and the fingerprint
        inputs, so the ordering can never drift from the actual data dependencies.

        Returns:
            tuple[str, ...]: Producer keys, de-duplicated, in first-seen order.
        """
        producers: list[str] = []
        for source in input_bindings(self.Input).values():
            if isinstance(source, FromSibling) and source.producer not in producers:
                producers.append(source.producer)
        return tuple(producers)

    def local_services(self) -> dict[str, Any]:
        """
        The services this node OWNS and pushes onto the registry for its subtree.

        Override to specialise the vertical axis at this level (deeper = more specialised). The base
        provides none.

        Returns:
            dict[str, Any]: Service name -> service, empty by default.
        """
        return {}

    def describe(self) -> NodeSchema:
        """
        Emit the self-describing schema for this node (children added by ``CompositeNode``).

        Includes the node's Config JSON schema when it declares one, so the discovery API can render
        the per-collection editing form for this node with zero hardcoded text.

        Returns:
            NodeSchema: Identity + dependencies + required services + config schema.
        """
        # Emit the config JSON schema only when the node declares a real Config (not the empty base).
        config_schema = self.Config.model_json_schema() if self.Config is not NodeConfig else None
        # Emit a chain slot (gate + provider catalog) for every ChainRef the node requires.
        chains = [self._chain_schema(ref) for ref in self.REQUIRES if isinstance(ref, ChainRef)]
        return NodeSchema(
            kind=self.KIND,
            key=self.key,
            name=self.name,
            description=self.description,
            consumes=list(self.consumes()),
            requires=[ref.name for ref in self.REQUIRES],
            config_schema=config_schema,
            chains=chains,
        )

    @staticmethod
    def _chain_schema(ref: ChainRef) -> ChainSchema:
        """
        Resolve a chain slot's discovery schema: the escalation gate + the provider catalog.

        The provider configs self-register on import (``@register(category)``), so importing the
        category package populates the catalog. Imports are lazy so the heavy provider packages are
        pulled only when a chain node is actually described.

        Args:
            ref (ChainRef): The chain slot declaration (name + category).

        Returns:
            ChainSchema: name + category + gate schema + the catalog of available providers.
        """
        # 1. Lazily import the category package so its provider configs register, then pull them.
        import importlib

        from common_libs.config.pipeline._registry import get_configs
        from common_libs.config.pipeline.chain_gate_config import ChainGateConfig

        importlib.import_module(f"common_libs.providers.{ref.category}")

        # 2. Build the provider catalog (each provider's config schema) + the gate schema.
        providers = [
            ProviderSchema(id=pid, config_schema=cls.model_json_schema())
            for pid, cls in get_configs(ref.category).items()
        ]
        return ChainSchema(
            name=ref.name,
            category=ref.category,
            gate_schema=ChainGateConfig.model_json_schema(),
            providers=providers,
        )


class CompositeNode(AbstractNode[InputT, OutputT], ABC, abstract=True):
    """
    A node whose work is its ordered children (pipeline over stages, stage over steps).

    A concrete composite declares its ``children`` and how to ``aggregate`` their outputs; the engine
    resolves each child's input from the sibling outputs, runs it, and applies its error policy.
    """

    @property
    @abstractmethod
    def children(self) -> list[AbstractNode]:
        """The ordered child nodes (the engine topo-orders them by their ``consumes``)."""
        ...

    def aggregate(self, child_outputs: dict[str, NodeOutput]) -> NodeOutput:
        """
        Combine the children's outputs into this composite's output.

        The default returns a structural ``CompositeOutput``; concrete composites override this to
        return their own typed output (e.g. the pipeline's final result).

        Args:
            child_outputs (dict[str, NodeOutput]): Child key -> its produced output.

        Returns:
            NodeOutput: This composite's output for the run.
        """
        return CompositeOutput(children=dict(child_outputs))

    def describe(self) -> NodeSchema:
        """Emit this composite's schema, recursing into its children."""
        schema = super().describe()
        schema.children = [child.describe() for child in self.children]
        return schema


class LeafNode(AbstractNode[InputT, OutputT], ABC, abstract=True):
    """
    A node that performs real work: it reads its typed input and returns its typed output.

    The leaf never touches scheduling/caching/errors — it receives a fully-resolved ``Scope`` and
    returns its ``Output``; the engine wraps it with tracking + error policy.
    """

    @abstractmethod
    async def execute(self, ctx: ContextBase) -> OutputT:
        """
        Do the node's work from its fully-resolved context.

        Args:
            ctx (ContextBase): The node's context — its resolved typed ``input`` + its required
                services (concrete nodes receive their own ``Context`` subclass).

        Returns:
            OutputT: This node's typed output.

        Raises:
            NodeError: A subclass-specific failure (the engine records it and applies the policy).
        """
        ...


__all__ = ["AbstractNode", "CompositeNode", "LeafNode"]
