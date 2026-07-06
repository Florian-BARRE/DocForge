# ====== Code Summary ======
# The config base of the OCR provider family. Deliberately empty: an OCR node runs on ONE figure
# and reports its confidence as its output SCORE — escalation to a stronger provider is a
# ScoreBelow TRANSITION on the graph, not a config knob. Children add their provider specifics
# (endpoint, api key, model…).

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseOcrConfig(NodeConfig):
    """Shared OCR config (children add their provider knobs; escalation lives on the graph)."""


__all__ = ["BaseOcrConfig"]
