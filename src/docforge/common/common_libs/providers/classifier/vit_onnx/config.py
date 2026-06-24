# ====== Code Summary ======
# Configuration class for the ViT ONNX figure classifier.
# Registered under the "classifier" category via @register("classifier").
# build() instantiates VitOnnxClassifier from the sibling module.

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import VitOnnxClassifier


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
        """
        Return this config unchanged — model_path/use_gpu are per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            VitOnnxConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — the ONNX model_path is supplied per-collection."""
        _ = cfg
        return True, "ViT-ONNX classifier · model_path per-collection"
