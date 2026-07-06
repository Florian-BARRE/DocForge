# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every embedder folder inside it, so each node self-registers
# simply by existing here — no manual list to maintain. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "embed",
    title="Embedding",
    description=(
        "Turns each chunk's enriched text into its Qdrant vectors (dense, and sparse when the provider supports it). Pick ONE embedder per pipeline."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
