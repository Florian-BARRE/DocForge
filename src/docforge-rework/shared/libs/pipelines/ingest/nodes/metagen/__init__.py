# ---------------------- Stage 6 - METAGEN ---------------------- #
# LLM-generated metadata for the contract's origin=GENERATED fields: the contract declares the
# fields (name, type, scope), the node config binds prompt + LLM per field, the field type forces
# the output through structured generation. Importing this stage imports every node folder.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "metagen",
    title="Metadata generation",
    description=(
        "Fills the contract's GENERATED metadata fields by LLM — one node per scope (document / chunk), each usable several times over field subsets with different models."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
