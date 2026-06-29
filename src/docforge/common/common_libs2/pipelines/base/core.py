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
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .context import CapabilityRef, Scope
from .io import CompositeOutput, FromSibling, NodeInput, NodeOutput, input_bindings
from .enums import ErrorPolicy, NodeKind
from .schema import NodeSchema
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
    REQUIRES: ClassVar[tuple[CapabilityRef, ...]] = ()

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

    def local_capabilities(self) -> dict[str, Any]:
        """
        The capabilities this node OWNS and pushes onto the registry for its subtree.

        Override to specialise the vertical axis at this level (deeper = more specialised). The base
        provides none.

        Returns:
            dict[str, Any]: Capability name -> capability, empty by default.
        """
        return {}

    def describe(self) -> NodeSchema:
        """
        Emit the self-describing schema for this node (children added by ``CompositeNode``).

        Returns:
            NodeSchema: Identity + dependencies + required capabilities.
        """
        return NodeSchema(
            kind=self.KIND,
            key=self.key,
            name=self.name,
            description=self.description,
            consumes=list(self.consumes()),
            requires=[ref.name for ref in self.REQUIRES],
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
    async def execute(self, scope: Scope[InputT]) -> OutputT:
        """
        Do the node's work from a fully-resolved scope.

        Args:
            scope (Scope[InputT]): The resolved typed input + the required capabilities.

        Returns:
            OutputT: This node's typed output.

        Raises:
            NodeError: A subclass-specific failure (the engine records it and applies the policy).
        """
        ...


__all__ = ["AbstractNode", "CompositeNode", "LeafNode"]
