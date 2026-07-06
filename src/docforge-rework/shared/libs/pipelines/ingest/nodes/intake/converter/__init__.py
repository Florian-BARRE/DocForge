# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every converter folder inside it, so each concrete converter
# self-registers simply by existing here. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "converter",
    title="Converter",
    description=(
        "Turns the accepted source into the pipeline's working PDF. Pick ONE converter per pipeline; alternatives are swapped, not combined."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
