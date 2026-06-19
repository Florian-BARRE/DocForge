# ====== Code Summary ======
# DoclingConfig: Pydantic provider config for the Docling parser backend.
# Decorated with @register("parser") for auto-discovery via the plugin registry.
# Exposes build() to instantiate DoclingBackend and merge_defaults() for deployment overrides.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from libs.core.contracts._registry import register
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from .core import DoclingBackend


@register("parser")
class DoclingConfig(BaseModel):
    """
    Configuration for the Docling PDF parser backend.

    Config id: "docling" — structural block extraction, table recognition, figure detection.

    Attributes:
        id: Provider discriminator — always "docling".
        use_gpu: Use GPU acceleration for Docling layout models when True.
    """

    _label: ClassVar[str] = "Docling — structural parser with table + figure detection"
    _category: ClassVar[str] = "parser"

    id: Literal["docling"] = "docling"
    use_gpu: bool = Field(default=False, description="Use GPU for Docling layout models.")

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Normalize flat provider spec dicts before field validation."""
        return _flatten_provider_spec(v)

    def build(self) -> DoclingBackend:
        """
        Instantiate DoclingBackend from this config.

        Returns:
            DoclingBackend: Configured backend instance.
        """
        return DoclingBackend(use_gpu=self.use_gpu)

    def merge_defaults(self, cfg: Any) -> DoclingConfig:
        """
        Merge deployment environment defaults into this config.

        Args:
            cfg: Runtime config object carrying optional ``DOCLING_USE_GPU`` flag.

        Returns:
            DoclingConfig: New config instance with merged values.
        """
        return self.model_copy(update={
            "use_gpu": self.use_gpu or getattr(cfg, "DOCLING_USE_GPU", False),
        })

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """
        Report availability of the Docling backend.

        Docling is always available — it is bundled in the container image.

        Args:
            cfg: Runtime config (unused — availability is unconditional).

        Returns:
            tuple[bool, str]: Always ``(True, "Default structural parser")``.
        """
        return True, "Default structural parser"
