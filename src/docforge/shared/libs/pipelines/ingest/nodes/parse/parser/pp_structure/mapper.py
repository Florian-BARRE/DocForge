# ====== Code Summary ======
# Translates a PP-StructureV3 sidecar response into the canonical DocumentIR — the pp_structure→IR
# adapter. The per-page block-contract skeleton (page walk, reading order, content slots, bbox
# normalization, heading tree) is the shared SidecarIRMapper; this class only binds the PP-StructureV3
# label vocabulary.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from ..sidecar_base import SidecarIRMapper

# ====== Local Project Imports ======
from .labels import PpStructureLabels


class PpStructureIRMapper(SidecarIRMapper):
    """Static adapter mapping a PP-StructureV3 sidecar response into the canonical DocumentIR."""

    logger = loggerplusplus.bind(identifier="PpStructureIRMapper")
    LOG_LABEL = "PP-Structure"
    LABEL_MAP = PpStructureLabels.LABEL_MAP
    HEADING_LEVELS = PpStructureLabels.HEADING_LEVELS


__all__ = ["PpStructureIRMapper"]
