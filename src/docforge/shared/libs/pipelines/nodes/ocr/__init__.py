# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every provider folder inside it, so each node self-registers
# simply by existing here — no manual list to maintain. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "ocr",
    title="OCR",
    description=(
        "Reads the text inside an image. Providers are meant for ESCALATION chains: a cheap local head, then score_below/on_failure edges to a robust tail, joined back with a from_first binding."
    ),
    mode=FamilyMode.CHAIN,
)
NodeRegistry.auto_import(__name__)
