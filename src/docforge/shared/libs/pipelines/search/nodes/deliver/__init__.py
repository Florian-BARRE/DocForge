# ---------------------- Search stage 8 — DELIVER ---------------------- #
# Reuses the EXISTING deliver family (shared with ingestion): the hits node closes a search pipeline
# by packaging the ranked hits into the SearchResult output contract. Registering the family here
# too (idempotently) keeps the search palette self-describing when ingestion is not imported; the
# metadata stays STAGE-moded and matches ingestion's.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "deliver",
    title="Delivery",
    description=(
        "Closes a pipeline by assembling the run's output into its delivery contract — the "
        "ingestion RunBundle, or the search SearchResult. Every pipeline ends here."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
