# ====== Code Summary ======
# Pydantic config for the Gotenberg converter provider.
# Registered under the "converter" discriminator via @register("converter").
# The build() method instantiates GotenbergConverter from this config.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .provider import GotenbergConverter


@register("converter")
class GotenbergConfig(BaseModel):
    """
    Configuration for the Gotenberg document converter.

    Config id: "gotenberg" — LibreOffice + Chromium conversion via the Gotenberg HTTP API.

    Attributes:
        id: Provider discriminator — always "gotenberg".
        base_url: Gotenberg service URL (e.g. http://gotenberg:3000).
        timeout_s: HTTP conversion timeout in seconds.
    """

    _label: ClassVar[str] = "Gotenberg — LibreOffice + Chromium PDF/DOCX/HTML converter"
    _category: ClassVar[str] = "converter"

    id: Literal["gotenberg"] = "gotenberg"
    base_url: str = Field(default="http://gotenberg:3000", description="Gotenberg service URL.")
    timeout_s: int = Field(default=120, ge=10, le=600, description="HTTP timeout in seconds.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> GotenbergConverter:
        """Instantiate GotenbergConverter from this config."""
        return GotenbergConverter(base_url=self.base_url, timeout_s=self.timeout_s)

    def merge_defaults(self, cfg: Any) -> GotenbergConfig:
        """Merge deployment env defaults (base_url from RUNTIME_CONFIG)."""
        return self.model_copy(update={
            "base_url": self.base_url or getattr(cfg, "GOTENBERG_URL", self.base_url),
            "timeout_s": self.timeout_s,
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Check Gotenberg availability — always available (no import check needed)."""
        base_url = getattr(cfg, "GOTENBERG_URL", "")
        return True, f"Gotenberg at {base_url}" if base_url else "URL configurable"
