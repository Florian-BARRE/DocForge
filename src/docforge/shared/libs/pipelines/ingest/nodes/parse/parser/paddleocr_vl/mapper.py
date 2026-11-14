# ====== Code Summary ======
# Translates a PaddleOCR-VL 1.6 sidecar response into the canonical DocumentIR — the paddleocr_vl→IR
# adapter. The PaddleOCR-VL sidecar (src/paddle_server, POST /vl-parse) emits the SAME per-page block
# contract the PP-StructureV3 sidecar does, so this class only binds the pp_structure label vocabulary
# to the shared SidecarIRMapper skeleton (unmapped labels — seal, footnote, aside_text, i.e.
# PaddleOCR-VL's own markdown_ignore_labels — are skipped); it stays a distinct class so
# paddleocr_vl is its own brick in the palette and execution trace.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ..pp_structure.labels import PpStructureLabels
from ..sidecar_base import SidecarIRMapper


class PaddleOcrVlIRMapper(SidecarIRMapper):
    """Static adapter mapping a PaddleOCR-VL 1.6 sidecar response into the canonical DocumentIR."""

    logger = loggerplusplus.bind(identifier="PaddleOcrVlIRMapper")
    LOG_LABEL = "PaddleOCR-VL"
    LABEL_MAP = PpStructureLabels.LABEL_MAP
    HEADING_LEVELS = PpStructureLabels.HEADING_LEVELS


__all__ = ["PaddleOcrVlIRMapper"]
