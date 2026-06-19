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
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .mistral_ocr import MistralOcrProvider


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
        return MistralOcrProvider(
            api_key=self.api_key,
            api_url=self.base_url,
            model=self.model,
            timeout_s=self.timeout_s,
        )

    def merge_defaults(self, cfg: Any) -> MistralOcrConfig:
        """Merge deployment env defaults for missing credentials/endpoints."""
        return self.model_copy(update={
            "api_key": self.api_key or getattr(cfg, "MISTRAL_OCR_API_KEY", ""),
            "base_url": self.base_url or getattr(cfg, "MISTRAL_OCR_API_URL", self.base_url),
            "model": self.model or getattr(cfg, "MISTRAL_OCR_MODEL", self.model),
            "timeout_s": self.timeout_s,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Always selectable — API key can be supplied on the fly from the playground."""
        has_key = bool(getattr(cfg, "MISTRAL_OCR_API_KEY", ""))
        if has_key:
            return True, "Cloud API · confidence=1.0"
        return True, "Select and paste your API key to enable on the fly"
