# ====== Code Summary ======
# Configuration class for the PaddleOCR local provider.
# Decorated with @register("ocr") so auto_import() discovers it automatically.
# Imports PaddleOcrProvider from the sibling module — provider does NOT import this file.
#
# GPU usage is a DEPLOYMENT decision (PADDLE_USE_GPU env + DeviceManager), NOT a per-collection
# pipeline knob — so `use_gpu` is intentionally NOT a Pydantic field. It is resolved from the
# deployment env in merge_defaults() and carried as a private runtime attribute to build().

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

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

    GPU usage is NOT exposed as a configurable field: whether PaddleOCR runs on GPU is a
    deployment decision driven by the ``PADDLE_USE_GPU`` env var (the GPU worker image sets it)
    and the central ``DeviceManager`` — never a per-collection setting. The resolved value is
    injected by ``merge_defaults`` and carried as a private attribute into ``build``.

    Attributes:
        id: Provider discriminator — always "paddle_ocr".
    """

    # extra="ignore" so a stored collection config still carrying a stale ``use_gpu`` key
    # (from before this field was removed) loads without raising — the key is simply dropped.
    model_config = ConfigDict(extra="ignore")

    _label: ClassVar[str] = "PaddleOCR — local GPU/CPU OCR (cost=0)"
    _category: ClassVar[str] = "ocr"

    id: Literal["paddle_ocr"] = "paddle_ocr"

    # Resolved from the deployment env in merge_defaults(); not a configurable pipeline field,
    # so it never appears in the JSON schema / discovery / UI. Defaults to False (CPU).
    _use_gpu: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> PaddleOcrProvider:
        """
        Instantiate PaddleOcrProvider from this config.

        The GPU flag comes from the deployment env (resolved in ``merge_defaults``), never
        from a per-collection pipeline field.

        Returns:
            PaddleOcrProvider: Configured provider instance.
        """
        return PaddleOcrProvider(use_gpu=self._use_gpu)

    def merge_defaults(self, cfg: Any) -> PaddleOcrConfig:
        """
        Merge deployment environment defaults into this config.

        Sources the GPU flag purely from the deployment env (``PADDLE_USE_GPU``) and stores
        it on the returned copy's private attribute for ``build`` to consume.

        Args:
            cfg: Runtime config object carrying the optional ``PADDLE_USE_GPU`` flag.

        Returns:
            PaddleOcrConfig: New config instance with the deployment GPU flag resolved.
        """
        merged = self.model_copy()
        merged._use_gpu = bool(getattr(cfg, "PADDLE_USE_GPU", False))
        return merged

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Available when the paddleocr package is installed (local, cannot be supplied over HTTP)."""
        try:
            import paddleocr  # noqa: F401
            return True, "olmOCR-2 · GPU/CPU · cost=0"
        except ImportError:
            return False, "paddleocr package not installed"
