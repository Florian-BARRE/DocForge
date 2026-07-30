# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every provider folder inside it, so each node self-registers
# simply by existing here — no manual list to maintain. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "vlm",
    title="Vision LLM",
    description=(
        "Describes an image (grounded on any prior OCR context) and closes an enrich branch with its entry. The system prompt IS the behaviour — one node per figure class, each with its own prompt."
    ),
    mode=FamilyMode.CHAIN,
)
NodeRegistry.auto_import(__name__)
