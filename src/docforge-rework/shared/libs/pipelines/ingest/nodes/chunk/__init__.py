# ---------------------- Stage 4 — CHUNK ---------------------- #
# Enriched IR → raw retrieval units: the chunker family (a METHOD is chosen like a provider).
# Importing this stage imports every node folder inside it.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "chunker",
    title="Chunker",
    description=(
        "Cuts the enriched IR into retrieval units. Pick ONE method per pipeline — they are alternative strategies over the same contract, not layers."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
