# ---------------------- Build-time errors -------------------- #
from .errors import ChainBuildError, PipelineBuildError

# ---------------------- Input contract ----------------------- #
from .models import ChainSpec, IngestBuildSpec, IngestClients

# ---------------------- Sub-builders ------------------------- #
from .chain_builder import ChainBuilder
from .splitter_builder import SplitterBuilder

# ---------------------- Config adapter ----------------------- #
from .db_adapter import IngestBuildSpecAdapter

# ---------------------- Public API --------------------------- #
# NOTE: the v1 IngestPipelineBuilder (builder/core.py) + the v1 IngestPipeline it drove are deleted;
# the flow pipeline is now built by common_libs.pipelines.build.FlowPipelineBuilder. The pieces below
# (chain builder, splitter builder, the typed spec + its DB adapter) are reused by that flow builder.
__all__ = [
    "PipelineBuildError",
    "ChainBuildError",
    "ChainSpec",
    "IngestClients",
    "IngestBuildSpec",
    "ChainBuilder",
    "SplitterBuilder",
    "IngestBuildSpecAdapter",
]
