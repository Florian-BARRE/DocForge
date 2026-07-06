# ---------------------- Ingestion-pipeline nodes, grouped by STAGE ---------------------- #
# One folder per major stage (ingest / parse / enrich / chunk - contextualize, metagen, embed
# to come), each importing its own node folders: everything self-registers by existing here.
from shared_libs.pipelines.registry import NodeRegistry

NodeRegistry.auto_import(__name__)
