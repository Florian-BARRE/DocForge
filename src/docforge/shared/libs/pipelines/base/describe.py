# ====== Code Summary ======
# The self-description payload a node hands to the backend-driven UI. It is what lets the UI
# carry zero hardcoded text: every label, help string, config field and I/O slot is read from
# here. A node's describe() returns one NodeDescription — the TYPE card (kind, labels, config
# schema, I/O). It is instance-free (usable for the palette); a BUILT pipeline's recursive tree is
# assembled by the explorer, which wraps each node's card with its instance data.
#
# `config_schema` is the raw JSON Schema of the node's ConfigModel (Pydantic's model_json_schema)
# — the UI turns each field into the right control (free string / enum / number) from it.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from .enums import NodeType
from .errors import ErrorPolicy


class IoSlot(BaseModel):
    """
    One typed slot of a node's CONSUMES or PRODUCES face.

    Attributes:
        name (str): Field name on the I/O model — the handle a graph binding targets.
        artefact_type (str): Shared-artefact type token (e.g. ``DocumentIR``) used for UI +
            validation.
        required (bool): Whether the slot must be satisfied for the node to run.
        description (str | None): Optional human hint shown in the UI.
    """

    name: str
    artefact_type: str
    required: bool = True
    description: str | None = None


class NodeDescription(BaseModel):
    """
    UI-facing description of a single node (recursive for groups via ``children``).

    Attributes:
        kind (str): Stable registry id of the node class.
        node_type (NodeType): ``ACTION`` or ``GROUP``.
        name (str): Human label.
        summary (str): One-line statement of what the node is for.
        how_it_works (str | None): Optional longer explanation.
        config_schema (dict): JSON Schema of the node's ConfigModel (drives the config form).
        consumes (list[IoSlot]): Typed input slots the node needs.
        produces (list[IoSlot]): Typed artefacts the node emits.
        error_policy (ErrorPolicy): The node's failure stance.
        unique_in_graph (bool): True when at most ONE instance of this node belongs in a graph
            (the UI badges it once placed; the validator rejects duplicates).
        selectable (bool): True when a user may pick this node as a stage METHOD from the palette.
            Internal wiring nodes (prep/apply/skip terminals a stage builder emits automatically)
            set it False so the discovery palette hides them, while they stay registered and
            describable for the graph engine.
        scored (bool): True when the node's output carries a quality score — the UI can offer a
            ``score_below`` escalation edge FROM this node (auto-derived from Produces).
        switch_fields (dict): Output fields meant for ``when_equals`` routing, with their closed
            value sets (e.g. a classifier's ``{"kind": [the five classes]}``) — the UI offers the
            ready-made switch branches.
    """

    kind: str
    node_type: NodeType
    name: str
    summary: str
    how_it_works: str | None = None
    config_schema: dict[str, Any] = Field(default_factory=dict)
    consumes: list[IoSlot] = Field(default_factory=list)
    produces: list[IoSlot] = Field(default_factory=list)
    error_policy: ErrorPolicy = ErrorPolicy.FAIL
    unique_in_graph: bool = False
    selectable: bool = True
    scored: bool = False
    switch_fields: dict[str, list[str]] = Field(default_factory=dict)


__all__ = ["IoSlot", "NodeDescription"]
