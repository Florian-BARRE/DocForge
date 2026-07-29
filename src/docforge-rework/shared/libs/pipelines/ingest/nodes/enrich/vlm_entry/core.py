# ====== Code Summary ======
# The vlm_entry node — the model-free terminal that closes a VLM chain. A VLM provider produces a
# SCORED entry ({entry, score}) so a ScoreBelow edge can escalate to the next provider; but a
# ForEach terminal must be single-slot ({entry} only). This node projects a VLM's scored output onto
# the uniform single-slot terminal — carrying the description, parsed table and OCR text through,
# spending nothing. Wired best-first off whichever chain step actually answered.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import EnrichmentEntry


class VlmEntryConfig(NodeConfig):
    """vlm_entry has no knob — it is a pure scored-entry → single-slot terminal projection."""


class VlmEntryConsumes(NodeInput):
    """Input: the entry a VLM chain produced (its score dropped at the terminal)."""

    entry: EnrichmentEntry = Field(
        description="The entry a VLM provider produced (description, table and OCR text aboard)."
    )


class VlmEntryProduces(NodeOutput):
    """Output: the branch's terminal entry (single slot, by the collection contract)."""

    entry: EnrichmentEntry = Field(
        description="The branch terminal: the VLM entry relayed unchanged, no model call."
    )


@NodeRegistry.register("enrich")
class VlmEntryNode(ActionNode):
    """Close a VLM chain by relaying its scored entry onto the uniform single-slot terminal."""

    KIND = "vlm_entry"
    NAME = "VLM entry"
    SUMMARY = "Close a VLM chain by relaying its entry onto the uniform terminal (no model call)."
    HOW_IT_WORKS = (
        "A VLM provider produces a SCORED entry so a score_below edge can escalate to the next "
        "provider — a two-slot output that cannot itself be a ForEach terminal. This node projects "
        "that entry onto the single-slot terminal every enrich branch converges on, relaying the "
        "description, parsed table and OCR text unchanged and spending nothing. It is wired "
        "best-first off whichever chain step answered."
    )
    SELECTABLE = False
    Config = VlmEntryConfig
    Consumes = VlmEntryConsumes
    Produces = VlmEntryProduces

    async def run(self, data: VlmEntryConsumes) -> VlmEntryProduces:
        """
        Relay the VLM's entry onto the uniform single-slot terminal.

        Args:
            data (VlmEntryConsumes): The entry a VLM chain produced.

        Returns:
            VlmEntryProduces: The same entry, now the branch's terminal artefact.
        """
        # 1. The VLM already built the entry — drop the score and relay it as the terminal.
        return VlmEntryProduces(entry=data.entry)


__all__ = ["VlmEntryNode", "VlmEntryConfig", "VlmEntryConsumes", "VlmEntryProduces"]
