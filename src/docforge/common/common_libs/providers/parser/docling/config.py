# ====== Code Summary ======
# DoclingConfig: Pydantic provider config for the Docling parser backend.
# Decorated with @register("parser") for auto-discovery via the plugin registry.
# Exposes build() to instantiate DoclingBackend and merge_defaults() for deployment overrides.
#
# GPU usage is a DEPLOYMENT decision (DOCLING_USE_GPU env + DeviceManager), NOT a per-collection
# pipeline knob — so `use_gpu` is intentionally NOT a Pydantic field. It is resolved from the
# deployment env in merge_defaults() and carried as a private runtime attribute to build().

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.pipeline.bricks.providers.parser.docling.core import DoclingBackend


@register("parser")
class DoclingConfig(BaseModel):
    """
    Configuration for the Docling PDF parser backend.

    Config id: "docling" — structural block extraction, table recognition, figure detection.

    GPU usage is NOT exposed as a configurable field: whether Docling runs on GPU is a
    deployment decision driven by the ``DOCLING_USE_GPU`` env var (the GPU worker image sets it)
    and the central ``DeviceManager`` — never a per-collection setting. The resolved value is
    injected by ``merge_defaults`` and carried as a private attribute into ``build``.

    Attributes:
        id: Provider discriminator — always "docling".
    """

    # extra="ignore" so a stored collection config still carrying a stale ``use_gpu`` key
    # (from before this field was removed) loads without raising — the key is simply dropped.
    model_config = ConfigDict(extra="ignore")

    _label: ClassVar[str] = "Docling — structural parser with table + figure detection"
    _category: ClassVar[str] = "parser"

    id: Literal["docling"] = "docling"

    # Resolved from the deployment env in merge_defaults(); not a configurable pipeline field,
    # so it never appears in the JSON schema / discovery / UI. Defaults to False (CPU).
    _use_gpu: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Normalize flat provider spec dicts before field validation."""
        return _flatten_provider_spec(v)

    def build(self) -> DoclingBackend:
        """
        Instantiate DoclingBackend from this config.

        The GPU flag comes from the deployment env (resolved in ``merge_defaults``), never
        from a per-collection pipeline field.

        Returns:
            DoclingBackend: Configured backend instance.
        """
        from common_libs.pipeline.bricks.providers.parser.docling.core import DoclingBackend  # lazy runtime brick (L3)
        return DoclingBackend(use_gpu=self._use_gpu)

    def merge_defaults(self, cfg: Any) -> DoclingConfig:
        """
        Merge deployment environment defaults into this config.

        Sources the GPU flag purely from the deployment env (``DOCLING_USE_GPU``) and stores
        it on the returned copy's private attribute for ``build`` to consume.

        Args:
            cfg: Runtime config object carrying the optional ``DOCLING_USE_GPU`` flag.

        Returns:
            DoclingConfig: New config instance with the deployment GPU flag resolved.
        """
        merged = self.model_copy()
        merged._use_gpu = bool(getattr(cfg, "DOCLING_USE_GPU", False))
        return merged

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
