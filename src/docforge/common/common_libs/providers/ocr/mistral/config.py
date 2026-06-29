# ====== Code Summary ======
# Configuration class for the Mistral OCR cloud API provider.
# Decorated with @register("ocr") so auto_import() discovers it automatically.
# Imports MistralOcrProvider from the sibling module — provider does NOT import this file.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.providers.ocr.mistral.provider import MistralOcrProvider


@register("ocr")
class MistralOcrConfig(BaseModel):
    """
    Configuration for the Mistral OCR cloud API provider.

    Config id: "mistral_ocr" — external cloud API, api_key required at build time.
    Positioned as the second link in an OCR escalation chain.

    Attributes:
        api_key: Mistral API key (empty = use deployment env default at merge time).
        base_url: Mistral API base URL.
        model: OCR model identifier.
        timeout_s: HTTP request timeout in seconds.
    """

    _label: ClassVar[str] = "Mistral OCR — cloud API (confidence=1.0, requires API key)"
    _category: ClassVar[str] = "ocr"

    id: Literal["mistral_ocr"] = "mistral_ocr"
    api_key: str = Field(default="", description="Mistral API key — merged from env if empty.")
    base_url: str = Field(default="https://api.mistral.ai/v1", description="Mistral API base URL.")
    model: str = Field(default="mistral-ocr-latest", description="OCR model identifier.")
    timeout_s: int = Field(default=60, ge=5, le=300, description="HTTP timeout in seconds.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> MistralOcrProvider:
        """Instantiate MistralOcrProvider — raises ValueError when api_key is empty."""
        if not self.api_key:
            raise ValueError(
                "MistralOcrConfig.build(): api_key is required. "
                "Call merge_defaults(cfg) first or supply the key explicitly."
            )
        from common_libs.pipeline.bricks.providers.ocr.mistral.provider import MistralOcrProvider  # lazy runtime brick (L3)
        return MistralOcrProvider(
            api_key=self.api_key,
            api_url=self.base_url,
            model=self.model,
            timeout_s=self.timeout_s,
        )

    def merge_defaults(self, cfg: Any) -> MistralOcrConfig:
        """
        Return this config unchanged — api_key/base_url/model are per-collection.

        Args:
            cfg: Unused — kept for call-site signature compatibility.

        Returns:
            MistralOcrConfig: This config, unchanged.
        """
        _ = cfg
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Report as usable — the Mistral API key is supplied per-collection."""
        _ = cfg
        return True, "Mistral OCR · API key per-collection"
