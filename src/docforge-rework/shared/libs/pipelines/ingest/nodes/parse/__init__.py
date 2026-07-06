# ---------------------- Stage 2 — PARSE ---------------------- #
# Raw document → COMPLETE DocumentIR: the parser family (structure) then figure_render (page
# rasterisation + crops embedded into the IR). Importing this stage imports every node folder.
from shared_libs.pipelines.registry import NodeRegistry

NodeRegistry.auto_import(__name__)
