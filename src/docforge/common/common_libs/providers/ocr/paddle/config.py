# ====== Code Summary ======
# Configuration class for the PaddleOCR local provider.
# Decorated with @register("ocr") so auto_import() discovers it automatically.
# Imports PaddleOcrProvider from the sibling module — provider does NOT import this file.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import PaddleOcrProvider


@register("ocr")
class PaddleOcrConfig(BaseModel):
    """
    Configuration for the PaddleOCR local provider.

    Config id: "paddle_ocr" — local GPU/CPU OCR, cost = 0.0, requires paddleocr package.

    Attributes:
        use_gpu: Run PaddleOCR on GPU (CUDA) when True.
    """

    _label: ClassVar[str] = "PaddleOCR — local GPU/CPU OCR (cost=0)"
    _category: ClassVar[str] = "ocr"

    id: Literal["paddle_ocr"] = "paddle_ocr"
    use_gpu: bool = Field(default=False, description="Use GPU (CUDA) for detection + recognition.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> PaddleOcrProvider:
        """Instantiate PaddleOcrProvider from this config."""
        return PaddleOcrProvider(use_gpu=self.use_gpu)

    def merge_defaults(self, cfg: Any) -> PaddleOcrConfig:
        """
        Return this config unchanged — use_gpu is per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            PaddleOcrConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Available when the paddleocr package is installed (local, cannot be supplied over HTTP)."""
        try:
            import paddleocr  # noqa: F401
            return True, "olmOCR-2 · GPU/CPU · cost=0"
        except ImportError:
            return False, "paddleocr package not installed"
