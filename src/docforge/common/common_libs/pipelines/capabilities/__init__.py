# ---------------------- Contract ----------------------------- #
from .base import Capability

# ---------------------- Families (scaffolding) --------------- #
# Concrete capability families land here as they are ported:
#   chain/        provider-escalation mechanism (gate + budget + call-cache)
#   providers/    parser, ocr, vlm, embed, rerank, llm, classifier, converter, device

# ---------------------- Public API --------------------------- #
__all__ = ["Capability"]
