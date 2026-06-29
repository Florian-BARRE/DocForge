# ------------------- Availability ------------------- #
from .availability import ProviderUnavailableError

# ------------------- Chain Builders ------------------- #
from .chain_builders import ChainBuilderHelpers

# ------------------- Chunk Stage Assembler ------------ #
from .chunk_stage_assembler import ChunkStageAssembler

# ------------------- Config Describer (recursive) ----- #
# Exported as `describe_config_tree` (NOT `describe`) because a sibling `describe.py` submodule
# would shadow a bare `describe` name on `from ...assembly import describe`.
from .config_describer import ConfigDescriberHelpers, ConfigNodeDict
from .config_describer import describe as describe_config_tree

# ------------------- Describe -------------------- #
from .describe import _params_from_model
from .describe_helpers import _param, _rules

# ------------------- Registry -------------------- #
from .registry import ProviderRegistry

# ------------------- Stage Descriptors -------------- #
from .stage_descriptors import StageDescriptorHelpers

# ------------------- Stage Registry (dynamic-architecture; PR-2) ----- #
# Only the registry + DAG primitives are exported here. `build_pipeline` lives in
# `stage_assembler` and is imported from that submodule directly — importing it here would create
# a cycle (stage_assembler imports the adapters, which import this package for @register_stage).
from .stage_registry import (
    ROOT_CONTEXT_KEYS,
    StageWiringError,
    auto_import_stages,
    get_stages,
    register_stage,
    topo_order,
    validate_wiring,
)

# ------------------- Public API ------------------- #
__all__ = [
    "ChainBuilderHelpers",
    "ChunkStageAssembler",
    "ConfigDescriberHelpers",
    "ConfigNodeDict",
    "ProviderRegistry",
    "ProviderUnavailableError",
    "StageDescriptorHelpers",
    "describe_config_tree",
    "_params_from_model",
    "_param",
    "_rules",
    # Stage registry (PR-2)
    "ROOT_CONTEXT_KEYS",
    "StageWiringError",
    "auto_import_stages",
    "get_stages",
    "register_stage",
    "topo_order",
    "validate_wiring",
]
