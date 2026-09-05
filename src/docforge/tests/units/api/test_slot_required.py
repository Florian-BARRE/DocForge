"""IoSlot.required is derived from the underlying field's optionality.

describe() must report a slot backed by an OPTIONAL field (``X | None``) or a DEFAULTED field
(a defaulted list, an optional with a default) as ``required=False``, and a genuinely mandatory
field as ``required=True`` — so discovery/UI can tell an optional input from a mandatory one.
Regression guard for the FAIBLE divergence where ``required`` was hardcoded True for every slot.
"""

from pydantic import BaseModel, Field

from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.base.io import NodeConfig, NodeInput, NodeOutput


class _FakeArtifact(BaseModel):
    """A throwaway artefact model used only to type the fake node's slots."""

    value: str = ""


class _FakeConfig(NodeConfig):
    """Empty config for the fake node."""


class _FakeConsumes(NodeInput):
    """CONSUMES face mixing mandatory, optional and defaulted slots."""

    mandatory: _FakeArtifact = Field(description="A genuinely required scalar slot.")
    optional_no_default: _FakeArtifact | None = Field(
        description="Optional slot (X | None) without an explicit default."
    )
    optional_with_default: _FakeArtifact | None = Field(
        default=None, description="Optional slot with an explicit None default."
    )
    defaulted_list: list[_FakeArtifact] = Field(
        default_factory=list, description="A list slot that may legitimately be empty."
    )
    mandatory_list: list[_FakeArtifact] = Field(description="A required list slot (no default).")


class _FakeProduces(NodeOutput):
    """PRODUCES face with a mandatory artefact and an optional one."""

    result: _FakeArtifact = Field(description="The mandatory output artefact.")
    maybe_extra: _FakeArtifact | None = Field(
        default=None, description="An output that may be absent."
    )


class _FakeNode(ActionNode):
    """A throwaway action node — defined but never registered, so it stays out of the palette."""

    KIND = "fake_slot_required"
    NAME = "Fake slot-required node"
    SUMMARY = "Exercises IoSlot.required derivation."
    Config = _FakeConfig
    Consumes = _FakeConsumes
    Produces = _FakeProduces

    async def run(self, data: NodeInput) -> NodeOutput:  # pragma: no cover - never executed
        return _FakeProduces(result=_FakeArtifact())


def _required_by_name(slots: list) -> dict[str, bool]:
    """Map each slot name to its reported ``required`` flag."""
    return {slot.name: slot.required for slot in slots}


def test_mandatory_scalar_slot_is_required() -> None:
    described = _FakeNode.describe()
    assert _required_by_name(described.consumes)["mandatory"] is True


def test_optional_slot_without_default_is_not_required() -> None:
    described = _FakeNode.describe()
    # X | None accepts None as a value, so the slot need not be satisfied even without a default.
    assert _required_by_name(described.consumes)["optional_no_default"] is False


def test_optional_slot_with_default_is_not_required() -> None:
    described = _FakeNode.describe()
    assert _required_by_name(described.consumes)["optional_with_default"] is False


def test_defaulted_list_slot_is_not_required() -> None:
    described = _FakeNode.describe()
    assert _required_by_name(described.consumes)["defaulted_list"] is False


def test_mandatory_list_slot_is_required() -> None:
    described = _FakeNode.describe()
    # list-ness must not leak into optionality: a list with no default is still mandatory.
    assert _required_by_name(described.consumes)["mandatory_list"] is True


def test_produces_optionality_is_derived_too() -> None:
    described = _FakeNode.describe()
    produces = _required_by_name(described.produces)
    assert produces["result"] is True
    assert produces["maybe_extra"] is False


def test_list_ness_label_is_unchanged() -> None:
    described = _FakeNode.describe()
    labels = {slot.name: slot.artefact_type for slot in described.consumes}
    assert labels["defaulted_list"] == "list[_FakeArtifact]"
    assert labels["mandatory"] == "_FakeArtifact"
    assert labels["optional_no_default"] == "_FakeArtifact"
