# ---------------------- Stage 1 - INTAKE ---------------------- #
# Validation + preparation of the source document: real-format detection, contract admission
# gate, conversion to PDF, system facts, content addressing. Importing this stage imports
# every node folder inside it.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "intake",
    title="Intake",
    description=(
        "Validation and preparation of the source document: each node plays one distinct role (real-format detection, contract admission, PDF facts, content addressing), wired once in stage order."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
