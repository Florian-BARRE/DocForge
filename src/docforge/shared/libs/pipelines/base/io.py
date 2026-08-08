# ====== Code Summary ======
# Data-plane contracts for the pipeline graph.
#
# Every node declares two typed faces here:
#   - CONSUMES (a NodeInput subclass)  — the typed slots it needs to run.
#   - PRODUCES (a NodeOutput subclass) — the typed artefacts it emits.
# Slot/artefact types come from the shared vocabulary in shared/libs/public_models; the graph
# validator decides producer→consumer compatibility by a plain subclass check over them.
#
# WIRING lives on the GRAPH, not the node class. A Binding maps one CONSUMES slot to a precise
# source — the output field of a specific upstream node (FromNode), the run-level input
# (FromRunInput), or the enclosing group's input (FromGroupInput). Because a binding names its
# source node explicitly, node 5 may consume node 1's output directly; the validator rejects
# only a downstream reference or a dependency cycle. Bindings are Pydantic models so they
# serialise straight into the stored pipeline blob and are resolved by the engine at run time.

# ====== Standard Library Imports ======
from enum import StrEnum
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

# ====== Internal Project Imports ======
# NodeConfig lives in public_models (the bottom vocabulary layer) and is re-exported here so every
# node config keeps importing it from ``pipelines.base`` unchanged — see [[public_models_pipelines_import_cycle]].
from shared_libs.public_models.base import NodeConfig, TimeoutConfig, TimeoutRetryConfig

# ====== Local Project Imports ======
from .execution import NodeUsage


class NodeInput(BaseModel):
    """
    Base class for a node's CONSUMES contract.

    Subclasses declare one field per required input slot, typed with a shared artefact model
    (e.g. ``ir: DocumentIR``). The field name is the slot a graph binding targets; the field
    type is what the graph validator checks candidate producers against.
    """

    model_config = ConfigDict(extra="forbid")


class NodeOutput(BaseModel):
    """
    Base class for a node's PRODUCES contract.

    Subclasses declare one field per emitted artefact, typed with a shared artefact model. A
    downstream node binds to one of these fields by name via ``FromNode``.

    ``_usage`` is a NON-field private attribute (never serialised, never a slot): a paid text-gen
    node stamps its per-call token usage onto the output it returns, and the engine lifts it onto
    the execution record. Being a PrivateAttr keeps it out of ``model_fields`` — so the ForEach
    single-slot terminal contract (``len(model_fields) == 1``) is untouched — and out of the record
    payload dump. Carrying it on the RETURNED output (a fresh instance per run) rather than on the
    node makes it race-free under a ForEach that runs one node instance concurrently over items.
    """

    model_config = ConfigDict(extra="forbid")

    _usage: NodeUsage | None = PrivateAttr(default=None)


class ScoredOutput(NodeOutput):
    """
    A PRODUCES contract that carries a self-assessed quality score.

    A node whose output can be quality-gated makes its Produces inherit this, so a ``ScoreBelow``
    transition can escalate when the score is too low (e.g. an OCR node's confidence). Nodes whose
    output has no meaningful score keep a plain ``NodeOutput``.

    Attributes:
        score (float): Normalised quality/confidence in [0, 1] the engine compares to a threshold.
    """

    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Self-assessed quality/confidence in [0, 1] — what a score_below escalation edge compares to its threshold.",
    )


class BindingSource(StrEnum):
    """Where a binding reads its value from — the discriminator of the Binding union."""

    NODE = "node"
    RUN = "run"
    GROUP = "group"
    FIRST = "first"


class FromNode(BaseModel):
    """
    Bind a CONSUMES slot to the output ``field_name`` of a PRECISE upstream node.

    The referenced node may sit anywhere upstream — node 5 consuming node 1's output is valid.
    The graph validator rejects only a downstream reference or a dependency cycle.

    Attributes:
        node_id (str): Identifier of the producing node in the same graph.
        field_name (str): Name of the field on that node's PRODUCES model to read.
    """

    source: Literal[BindingSource.NODE] = BindingSource.NODE
    node_id: str
    field_name: str


class FromRunInput(BaseModel):
    """
    Bind a CONSUMES slot to a field of the pipeline's run-level input.

    Attributes:
        field_name (str): Name of the field on the run input to read.
    """

    source: Literal[BindingSource.RUN] = BindingSource.RUN
    field_name: str


class FromGroupInput(BaseModel):
    """
    Bind a CONSUMES slot to a field exposed by the enclosing group's input.

    Lets a child node read an artefact handed down by its parent group rather than by a
    sibling, keeping sub-graphs reusable across pipelines.

    Attributes:
        field_name (str): Name of the field on the group input to read.
    """

    source: Literal[BindingSource.GROUP] = BindingSource.GROUP
    field_name: str


class FromFirst(BaseModel):
    """
    Bind a CONSUMES slot to the FIRST candidate node that actually produced an output.

    The convergence join of branched graphs: after an escalation (a ScoreBelow/OnFailure fork),
    exactly one of the alternative producers ran — list them best-first and the slot reads
    whichever answered. Every candidate is validated like a plain FromNode (upstream, field,
    type-compatible).

    Attributes:
        candidates (list[FromNode]): The possible sources, in priority order.
    """

    source: Literal[BindingSource.FIRST] = BindingSource.FIRST
    candidates: list[FromNode] = Field(min_length=1)


# Discriminated union — Pydantic selects the right marker from the ``source`` tag on load.
type Binding = Annotated[
    FromNode | FromRunInput | FromGroupInput | FromFirst, Field(discriminator="source")
]


__all__ = [
    "NodeConfig",
    "TimeoutConfig",
    "TimeoutRetryConfig",
    "NodeInput",
    "NodeOutput",
    "ScoredOutput",
    "BindingSource",
    "FromNode",
    "FromRunInput",
    "FromGroupInput",
    "FromFirst",
    "Binding",
]
