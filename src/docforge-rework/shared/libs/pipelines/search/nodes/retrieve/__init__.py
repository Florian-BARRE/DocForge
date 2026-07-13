# ---------------------- Search stage 4 — RETRIEVE ---------------------- #
# The retrieve family: pull the candidate chunk pool from the collection's store through the bound
# CollectionReadPort (never a direct store import). The default method is one server-side hybrid
# call (dense+sparse fused with RRF); the per-modality methods are future decompositions.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "retrieve",
    title="Retrieve",
    description=(
        "Pulls the candidate pool from the collection's store via the read port (the disabled-point "
        "exclusion is baked in, unbypassable). The hybrid method fuses dense+sparse server-side; the "
        "dense/sparse methods are future per-modality pools joined by a fuse step."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
