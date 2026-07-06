# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every parser folder inside it, so each concrete parser self-registers
# simply by existing here — no manual list to maintain. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "parser",
    title="Parser",
    description=(
        "Extracts the document's structure into the canonical IR. Pick ONE parser as the head; a stronger one may follow it through a score_below escalation edge."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
