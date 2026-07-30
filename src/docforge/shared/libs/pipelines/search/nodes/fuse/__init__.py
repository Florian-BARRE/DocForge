# ---------------------- Search stage 5 — FUSE ---------------------- #
# The fuse family: merge the per-modality candidate pools (once retrieve is decomposed) into one
# scored pool. Entirely future — the default graph uses server-side hybrid fusion instead. Registered
# for discoverability. Importing this family imports its placeholder module.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "fuse",
    title="Fuse",
    description=(
        "Merges decomposed per-modality candidate pools (dense/sparse) into one scored pool — RRF "
        "or weighted. Only used when retrieve is decomposed; the default graph fuses server-side."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
