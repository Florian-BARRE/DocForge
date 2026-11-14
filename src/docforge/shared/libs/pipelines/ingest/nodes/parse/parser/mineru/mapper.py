# ====== Code Summary ======
# Translates a MinerU2.5-Pro sidecar response into the canonical DocumentIR — the mineru→IR adapter.
# The MinerU sidecar (src/mineru_server, POST /parse) emits the SAME per-page block contract the
# PP-StructureV3 / PaddleOCR-VL sidecars do and already resolved MinerU's `type`/`text_level` into the
# pp_structure-style labels (title/paragraph_title/subsection preserve H1/H2/H3, table→html,
# equation→formula latex, image/chart→figure), emitting bboxes in a 0–1000 space with
# image_width/height=1000 so the shared divide-by-dims yields [0, 1] unchanged. So this class only
# binds the pp_structure label vocabulary to the shared SidecarIRMapper skeleton; it stays a distinct
# class so mineru is its own brick in the palette and execution trace.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ..pp_structure.labels import PpStructureLabels
from ..sidecar_base import SidecarIRMapper


class MineruIRMapper(SidecarIRMapper):
    """Static adapter mapping a MinerU2.5-Pro sidecar response into the canonical DocumentIR."""

    logger = loggerplusplus.bind(identifier="MineruIRMapper")
    LOG_LABEL = "MinerU"
    LABEL_MAP = PpStructureLabels.LABEL_MAP
    HEADING_LEVELS = PpStructureLabels.HEADING_LEVELS


__all__ = ["MineruIRMapper"]
