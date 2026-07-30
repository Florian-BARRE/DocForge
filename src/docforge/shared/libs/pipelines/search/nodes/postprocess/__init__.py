# ---------------------- Search stage 7 — POST-PROCESS ---------------------- #
# The post-process family: turn the ranked candidate pool into the final hit set — hydrate the rich
# chunk fields (the default, unavoidable step) and, later, dedup by document, diversify (MMR),
# expand to parents (small-to-big) or assemble a context. Importing this family imports its folders.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "postprocess",
    title="Post-process",
    description=(
        "Shapes the ranked pool into the delivered hits: hydrate the rich chunk fields from Postgres "
        "(via the read port), and — later — dedup by document, diversify with MMR, expand to parent "
        "chunks, or assemble a context. Stack the steps that apply."
    ),
    mode=FamilyMode.STACKABLE,
)
NodeRegistry.auto_import(__name__)
