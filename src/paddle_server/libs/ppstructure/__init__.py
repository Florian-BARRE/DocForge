# ------------------- Service ------------------- #
from .service import PpStructureService

# ------------------- Public API ------------------- #
# NOTE: `revision.PADDLE_PIN_INFO` is intentionally NOT re-exported — it is a documentation-only
# reference (the version-drift rationale cross-linked from both normalizers), not a value consumed
# at runtime. See revision.py.
__all__ = [
    "PpStructureService",
]
