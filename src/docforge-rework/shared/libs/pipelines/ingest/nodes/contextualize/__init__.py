# ---------------------- Stage 5 - CONTEXTUALIZE ---------------------- #
# Chunk-text enrichment for retrieval: STACKABLE methods sharing one face ({chunks} -> {chunks}),
# chained in the graph — the wiring order is the order the context pieces accumulate in.
# Importing this stage imports every method folder inside it.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "contextualize",
    title="Contextualize",
    description=(
        "Grows each chunk's retrieval context. The methods STACK: chain the ones you want, and the wiring order is the order their prefixes accumulate in."
    ),
    mode=FamilyMode.STACKABLE,
)
NodeRegistry.auto_import(__name__)
