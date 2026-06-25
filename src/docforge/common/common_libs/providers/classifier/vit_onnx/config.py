# ====== Code Summary ======
# Configuration class for the ViT ONNX figure classifier.
# Registered under the "classifier" category via @register("classifier").
# build() instantiates VitOnnxClassifier from the sibling module.
#
# GPU usage is a DEPLOYMENT decision (VIT_USE_GPU env + DeviceManager), NOT a per-collection
# pipeline knob — so `use_gpu` is intentionally NOT a Pydantic field. It is resolved from the
# deployment env in merge_defaults() and carried as a private runtime attribute to build().
# `model_path` remains a per-collection field (the ONNX model file is supplied per collection).

from __future__ import annotations

import os
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import VitOnnxClassifier


@register("classifier")
class VitOnnxConfig(BaseModel):
    """
    Configuration for the ViT ONNX figure classifier.

    Config id: "vit_onnx" — requires an ONNX model file on disk.

    GPU usage is NOT exposed as a configurable field: whether the ONNX session uses the CUDA
    execution provider is a deployment decision driven by the ``VIT_USE_GPU`` env var (the GPU
    worker image sets it) and the central ``DeviceManager`` — never a per-collection setting.
    The resolved value is injected by ``merge_defaults`` and carried as a private attribute into
    ``build``. ``model_path`` stays a per-collection field — it points at the deployed model file.

    Attributes:
        id: Provider discriminator — always "vit_onnx".
        model_path: Filesystem path to the .onnx model file (per-collection).
    """

    # extra="ignore" so a stored collection config still carrying a stale ``use_gpu`` key
    # (from before this field was removed) loads without raising — the key is simply dropped.
    model_config = ConfigDict(extra="ignore")

    _label: ClassVar[str] = "vit_onnx — ViT ONNX figure classifier (accurate, requires model file)"
    _category: ClassVar[str] = "classifier"

    id: Literal["vit_onnx"] = "vit_onnx"
    model_path: str = Field(default="", description="Path to the .onnx model file.")

    # Resolved from the deployment env in merge_defaults(); not a configurable pipeline field,
    # so it never appears in the JSON schema / discovery / UI. Defaults to False (CPU).
    _use_gpu: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> VitOnnxClassifier:
        """
        Instantiate VitOnnxClassifier from this config.

        The GPU flag comes from the deployment env (resolved in ``merge_defaults``), never
        from a per-collection pipeline field.

        Returns:
            VitOnnxClassifier: Configured classifier instance.

        Raises:
            ValueError: When ``model_path`` is empty or does not point to an existing file.
        """
        if not self.model_path or not os.path.exists(self.model_path):
            raise ValueError(
                f"VitOnnxConfig.build(): model_path not found: {self.model_path!r}. "
                f"Provide a valid path to a .onnx classifier model file."
            )
        return VitOnnxClassifier(model_path=self.model_path, use_gpu=self._use_gpu)

    def merge_defaults(self, cfg: Any) -> VitOnnxConfig:
        """
        Merge deployment environment defaults into this config.

        Sources the GPU flag purely from the deployment env (``VIT_USE_GPU``) and stores it on
        the returned copy's private attribute for ``build`` to consume. ``model_path`` is left
        untouched — it is a per-collection value.

        Args:
            cfg: Runtime config object carrying the optional ``VIT_USE_GPU`` flag.

        Returns:
            VitOnnxConfig: New config instance with the deployment GPU flag resolved.
        """
        merged = self.model_copy()
        merged._use_gpu = bool(getattr(cfg, "VIT_USE_GPU", False))
        return merged

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — the ONNX model_path is supplied per-collection."""
        _ = cfg
        return True, "ViT-ONNX classifier · model_path per-collection"
