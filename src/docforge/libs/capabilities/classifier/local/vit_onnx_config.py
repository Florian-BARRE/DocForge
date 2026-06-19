# ====== Code Summary ======
# Configuration class for the ViT ONNX figure classifier.
# Registered under the "classifier" category via @register("classifier").
# build() instantiates VitOnnxClassifier from the sibling module.

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .vit_onnx import VitOnnxClassifier


@register("classifier")
class VitOnnxConfig(BaseModel):
    """
    Configuration for the ViT ONNX figure classifier.

    Config id: "vit_onnx" — requires an ONNX model file on disk.

    Attributes:
        model_path: Filesystem path to the .onnx model file.
        use_gpu: Use ONNX Runtime GPU (CUDA) execution provider.
    """

    _label: ClassVar[str] = "vit_onnx — ViT ONNX figure classifier (accurate, requires model file)"
    _category: ClassVar[str] = "classifier"

    id: Literal["vit_onnx"] = "vit_onnx"
    model_path: str = Field(default="", description="Path to the .onnx model file.")
    use_gpu: bool = Field(default=False, description="Use ONNX Runtime GPU provider.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> VitOnnxClassifier:
        """Instantiate VitOnnxClassifier from this config."""
        import os
        if not self.model_path or not os.path.exists(self.model_path):
            raise ValueError(
                f"VitOnnxConfig.build(): model_path not found: {self.model_path!r}. "
                f"Provide a valid path to a .onnx classifier model file."
            )
        return VitOnnxClassifier(model_path=self.model_path, use_gpu=self.use_gpu)

    def merge_defaults(self, cfg: Any) -> VitOnnxConfig:
        """Return a copy with defaults merged from runtime config when fields are unset."""
        return self.model_copy(update={
            "model_path": self.model_path or getattr(cfg, "CLASSIFIER_ONNX_MODEL_PATH", ""),
            "use_gpu": self.use_gpu or getattr(cfg, "CLASSIFIER_USE_GPU", False),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Available when the ONNX model file is present on disk."""
        import os
        path = getattr(cfg, "CLASSIFIER_ONNX_MODEL_PATH", "")
        if path and os.path.exists(path):
            return True, f"ViT ONNX · accurate · model at {path}"
        return False, f"ONNX model not found at {path!r} — set CLASSIFIER_ONNX_MODEL_PATH"
