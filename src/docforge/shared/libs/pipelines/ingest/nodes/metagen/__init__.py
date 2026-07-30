# ---------------------- Stage 6 - METAGEN ---------------------- #
# LLM-generated metadata for the contract's origin=GENERATED fields: the contract declares the fields
# (name, type, scope). The model call is externalised into the generic structgen chain, so each scope
# is a PREP node (emits one GenerationRequest per call group), an APPLY node (merges the produced
# values back) and a fail-soft SKIP terminal. Importing this stage imports every node folder.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "metagen",
    title="Metadata generation",
    description=(
        "Fills the contract's GENERATED metadata fields per scope (document / chunk): a prep node "
        "emits the structured-generation requests, a structgen chain fulfils them, an apply node "
        "merges the values back, and a skip terminal drops a failed request's fields."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
