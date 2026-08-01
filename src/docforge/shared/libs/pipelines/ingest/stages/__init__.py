# ---------------------- Canonical skeleton ---------------------- #
from .spec import FigureBranch, StageKey, StageKind, StageMeta, StageSpecs

# ---------------------- View + action models ---------------------- #
from .models import (
    ChainStep,
    ChainView,
    DisableStage,
    EnableStage,
    SetChain,
    SetProvider,
    SetStack,
    SetStageConfig,
    StackMethod,
    StageAction,
    StageCatalog,
    StageView,
)

# ---------------------- State + assembly ---------------------- #
from .state import ChainSpec, PipelineState, default_state, light_state
from .assembler import IngestAssembler
from .reader import StateReader
from .normalizer import ENGINE_BLOB_VERSION, BlobNormalizationError, BlobNormalizer

# ---------------------- View + compiler ---------------------- #
from .view import StageViewer
from .compiler import StageCompiler

# ------------------- Public API ------------------- #
__all__ = [
    # skeleton
    "StageKind",
    "StageKey",
    "StageMeta",
    "FigureBranch",
    "StageSpecs",
    # view + action models
    "ChainStep",
    "ChainView",
    "StackMethod",
    "StageView",
    "StageCatalog",
    "EnableStage",
    "DisableStage",
    "SetProvider",
    "SetStageConfig",
    "SetChain",
    "SetStack",
    "StageAction",
    # state + assembly
    "ChainSpec",
    "PipelineState",
    "default_state",
    "light_state",
    "IngestAssembler",
    "StateReader",
    "BlobNormalizer",
    "BlobNormalizationError",
    "ENGINE_BLOB_VERSION",
    # view + compiler
    "StageViewer",
    "StageCompiler",
]
