# ---------------------- Stage 8 - DELIVER ---------------------- #
# The pipeline's output contract: the bundle node closes every ingestion pipeline by gathering
# the run's persistables into ONE RunBundle. Importing this stage imports every node folder.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "deliver",
    title="Delivery",
    description=(
        "Closes the pipeline: the bundle node assembles everything the run produced into the "
        "RunBundle the worker persists. Every ingestion pipeline ends here."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
