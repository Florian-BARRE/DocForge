# ====== Code Summary ======
# The config layer of a node — the per-COLLECTION, serialisable settings a node is BUILT with (as
# opposed to its per-document Input, which is the data it processes). A node declares ONE
# ``Config`` ClassVar (a NodeConfig subclass) the same way it declares Input/Output/Context/Error;
# the assembler reads the collection's stored JSON, instantiates each node's Config, and passes it to
# the node's __init__. The config is SELF-DESCRIBING: describe() emits each node's Config JSON schema
# so the discovery API renders the editing form with zero hardcoded text. Config is immutable once
# built (frozen) and strict (extra keys rejected) so an out-of-contract value fails fast.
#
# The hierarchy mirrors the node tree (ConfigBase -> the three KIND bases -> per-node configs named
# by path, e.g. IngestStageChunkConfig), exactly like the context hierarchy.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict


class NodeConfig(BaseModel):
    """
    Base for a node's configuration — serialisable, discovery-driven, immutable.

    The empty base means "this node has no configurable knobs"; concrete nodes subclass the matching
    KIND base and add fields. Every field SHOULD carry a ``Field(description=...)`` so the discovery
    payload can label it in the UI.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class PipelineConfigBase(NodeConfig):
    """Base config for a pipeline-level node."""


class StageConfigBase(NodeConfig):
    """Base config for a stage-level node."""


class StepConfigBase(NodeConfig):
    """Base config for a step-level node."""


__all__ = ["NodeConfig", "PipelineConfigBase", "StageConfigBase", "StepConfigBase"]
