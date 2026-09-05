"""AutoWire types a ForEach's ``items`` from the SAME collection-contract rule the validator uses:
every body terminal must produce the same single Artifact. A body whose terminals AGREE auto-wires a
downstream list consumer to the loop's ``items``; a body whose terminals DISAGREE types to no item
(None) — so AutoWire refuses the wire the validator would reject, instead of adopting the first
terminal's type (the divergence this guards)."""

from shared_libs.pipelines.base import FromNode, FromRunInput, Transition
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
)
from shared_libs.pipelines.edit.wiring import AutoWire
from shared_libs.pipelines.registry import NodeRegistry


def _make(*terminals: ActionNodeBlob) -> tuple[GroupNodeBlob, type]:
    """A container (ForEach over ``terminals`` → chained enrich_apply) and the consumer's class.

    enrich_apply consumes ``entries: list[EnrichmentEntry]`` — the slot AutoWire will (or will not)
    bind to the loop's ``items`` depending on whether the body terminals type uniformly.
    """
    container = GroupNodeBlob(
        id="root",
        nodes=[
            ForEachNodeBlob(
                id="loop",
                over=FromRunInput(field_name="figures"),
                item_field="figure",
                body=GroupNodeBlob(id="loop_body", nodes=list(terminals)),
            ),
            ActionNodeBlob(id="apply", family="enrich", kind="enrich_apply"),
        ],
        transitions=[Transition(from_node_id="loop", to_node_id="apply")],
    )
    return container, NodeRegistry.get("enrich", "enrich_apply")


def test_autowire_wires_items_when_body_terminals_agree() -> None:
    """Uniform body terminals (both EnrichmentEntry) → the loop's items feeds the list consumer."""
    container, node_class = _make(
        ActionNodeBlob(id="t_fig", family="enrich", kind="figure_entry"),
        ActionNodeBlob(id="t_vlm", family="enrich", kind="vlm_entry"),
    )
    bindings = AutoWire.bindings_for(container, "apply", node_class)
    assert "entries" in bindings
    assert isinstance(bindings["entries"], FromNode)
    assert bindings["entries"].node_id == "loop"
    assert bindings["entries"].field_name == "items"


def test_autowire_refuses_items_when_body_terminals_disagree() -> None:
    """Disagreeing terminals (EnrichmentEntry vs GeneratedDocumentMeta) → no item type, no wire.

    Before the fix AutoWire typed items from the FIRST terminal (EnrichmentEntry) and would still
    bind ``entries`` — a wire the validator's uniformity rule (FOREACH_INVALID_BODY) rejects.
    """
    container, node_class = _make(
        ActionNodeBlob(id="t_fig", family="enrich", kind="figure_entry"),
        ActionNodeBlob(id="t_doc", family="metagen", kind="document_apply"),
    )
    bindings = AutoWire.bindings_for(container, "apply", node_class)
    assert "entries" not in bindings
