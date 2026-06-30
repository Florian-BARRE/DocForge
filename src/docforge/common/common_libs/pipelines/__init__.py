# The v1 node-engine (base node machinery + engine/) is deleted — ingestion runs on the flow engine
# (common_libs.pipelines.flow). What survives at this top level is the per-collection CONFIG CONTRACTS
# the stage Config classes subclass (the self-describing, frozen settings the builder instantiates).
# Everything else is imported from its own package: flow / build / builder / capabilities / the stage
# packages (ingest, parse, enrich, chunk, contextualize, metagen, embed_index).

# ---------------------- Config contracts --------------------- #
from .base import NodeConfig, PipelineConfigBase, StageConfigBase, StepConfigBase

# ---------------------- Public API --------------------------- #
__all__ = [
    "NodeConfig",
    "PipelineConfigBase",
    "StageConfigBase",
    "StepConfigBase",
]
